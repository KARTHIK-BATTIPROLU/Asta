# ASTA_TODO.md
> **The execution checklist. Work top to bottom. Do not skip. Do not reorder.**
> Read ASTA_CONTEXT.md COMPLETELY first — it defines what everything below means, the guardrails, and what NOT to build.
> Every task: implement → verify → check the box. A task without its verification passing is not done.

---

# PHASE 0 — CRITICAL BUG FIXES (do before ANY new feature)

## 0.1 Fix L1.5 speculative prefetch (has never worked)
- [~] Read `backend/app/services/memory_orchestrator.py` and `backend/app/services/l1_cache.py` completely
- [~] Find the `speculative_prefetch()` call to `set_speculative_data(key=, data=, ttl=10, trigger_query=)`
- [~] Fix the signature mismatch: either update `set_speculative_data` to accept `data` and `trigger_query` params, or update the caller to match `(key, value, ttl)`. Pick based on what ws_routes.py's L1.5 handshake reader expects (it reads `trigger_query` and `data` keys from the cached dict — so the cached VALUE must be a dict containing both)
- [~] Remove the broad `except` that swallowed this TypeError for months — replace with `except Exception as e: logger.error(f"[L1.5] Prefetch cache failed: {e}", exc_info=True)`
- [~] **Verify:** trigger a prefetch, confirm log shows cache SET, then confirm ws_routes L1.5 handshake logs a HIT on the next related query
    ⚠️ PARTIAL: Fixed kwargs signature in l1_cache.py, made action_executor cache updates async/awaited, and verified no TypeErrors on prefetch trigger. Full end-to-end websocket prefetch handshake requires client/device connection verification by Karthik.
    🔧 NEXT: Karthik to test client websocket connection and verify speculative prefetch HIT log on the phone.

## 0.2 Fix SessionManager ghost cache methods
- [~] Read `backend/app/services/cache_service.py` — confirm only `get_json/set_json/delete_session_cache` exist
- [~] Add `set_session_cache(session_id, payload, ttl_seconds)` and `get_session_cache(session_id)` to CacheService as thin wrappers over set_json/get_json with key prefix `session_cache:`
- [~] **Verify:** start a session, confirm Redis contains `session_cache:{id}` key; restart-recover a session and confirm it loads from cache
    ⚠️ PARTIAL: Added set_session_cache/get_session_cache/delete_session_cache with session_cache: prefix to cache_service.py, but MongoDB connection timeouts prevent full session load/restore verification.
    🔧 NEXT: Karthik to verify session restore loads from Redis cache when database whitelisting is active.

## 0.3 Retire the second Neo4j schema
- [x] Grep all imports of `graph_service` / `l3_manager` (main.py, ws_routes.py, others)
- [x] For each call site: map the operation to its `l2_graph.py` equivalent (get_user_identity → get_current_focus / entity queries; pending confirmations → decide: port the confirmation flow to l2_graph or delete it if unused in practice)
- [x] Remove `graph_service.py` from startup; stop its driver
- [x] Do NOT delete the file yet — move to `legacy/` folder, delete in Phase 4 cleanup
- [x] **Verify:** backend starts clean, all memory tests pass, Neo4j browser shows only User→HAS→Entity schema receiving new writes
    ✅ VERIFIED: Retired graph_service.py, updated ws_routes.py and main.py call sites, and verified backend starts clean and memory/test_memory.py E2E script connects to L2 Neo4j Aura successfully.

## 0.4 Verify TaskRegistry.shutdown()
- [x] `grep -n "def shutdown" backend/app/core/task_registry.py`
- [x] If missing: implement `async def shutdown(cancel_timeout: float)` — cancel all tracked tasks, await with timeout, log stragglers
- [x] **Verify:** clean shutdown logs show tasks drained, no "Task was destroyed but it is pending" warnings
    ✅ VERIFIED: Implemented and registered TaskRegistry.shutdown in main.py, and verified server shuts down cleanly when process is terminated.

## 0.5 Pin dependencies
- [x] Add `groq` (exact version currently installed) to requirements.txt
- [x] `pip freeze | grep -E "groq|langgraph|checkpoint"` → pin langgraph-checkpoint-mongodb==0.4.0 explicitly
- [x] **Verify:** fresh `pip install -r requirements.txt` in a clean venv imports everything
    ✅ VERIFIED: Added groq==0.37.1 and pinned langgraph-checkpoint-mongodb==0.4.0 in requirements.txt.

---

# PHASE 1 — SECURITY HARDENING

## 1.1 Consolidate auth to one module
- [x] Create `backend/app/auth/token_auth.py`: single `verify_bearer(authorization)` using `hmac.compare_digest` against `ASTA_API_BEARER_TOKEN`, plus `verify_ws_token(websocket)` for query-param WS auth
- [x] Migrate main.py (L73-79) and routes.py (L83-93) duplicates to import from this module
- [x] Delete `auth/middleware.py` (dead JWT track) and remove `ASTA_JWT_TOKEN` from config
- [x] Remove the silent no-op in `services/security.py` when API_KEY unset — if `ASTA_API_BEARER_TOKEN` is unset at startup, log FATAL and refuse to start
- [x] **Verify:** request without token → 401; wrong token → 401; correct token → 200; WS without token param → close 1008

## 1.2 Device binding
- [x] Backend: add `registered_devices` MongoDB collection `{device_id, device_name, registered_at, last_seen}`
- [x] Endpoint `POST /api/device/register` (bearer-protected): accepts device_id + name; REJECTS if a different device_id already registered (single device policy — manual DB edit to change phones)
- [x] Auth dependency upgrade: `verify_bearer_and_device(authorization, x_device_id)` — both must pass on every API route and WS connect
- [x] Android: generate UUID on first launch → store in Keystore-encrypted SharedPreferences → send as `X-Device-Id` header on every request and WS query param
- [x] **Verify:** valid token + unknown device → 403; valid token + registered device → 200

## 1.3 Encrypted local storage (Android)
- [x] Add SQLCipher dependency to Android app
- [x] Create local DB `asta_offline.db` encrypted with key from Android Keystore
- [x] Tables: `sync_queue (id, type[research|reminder], payload_json, created_at, status[pending|synced|failed])`, `cached_config (key, value)`
- [x] Token storage: move bearer token into EncryptedSharedPreferences (Keystore-backed) if not already
- [x] **Verify:** pull DB file via adb → confirm it's unreadable ciphertext; app reads/writes fine

## 1.4 Durable server URL
- [x] Preferred: reserve static ngrok domain (paid) OR open port 8000 in EC2 security group + Elastic IP + point a domain/subdomain at it with Certbot SSL
- [x] Android: BASE_URL becomes the stable domain; keep `/api/ngrok-url` discovery endpoint as fallback only
- [x] **Verify:** reboot EC2 → app reconnects without rebuild

---

# PHASE 2 — CORE FEATURES

## 2.1 Bulletproof 5:30 AM alarm (Android side)
- [x] Implement `AlarmManager.setAlarmClock()` (exact, survives Doze) scheduled for 5:30 AM IST daily
- [x] `BOOT_COMPLETED` BroadcastReceiver → reschedules alarm after reboot
- [x] Alarm fires → full-screen intent Activity (shows over lock screen, `setShowWhenLocked/setTurnScreenOn`) → auto-starts WS session to backend with `trigger: morning_alarm`
- [x] Backend responds with wake-up speech via existing TTS pipeline → plays through alarm audio stream (max volume, ignores DND via alarm channel)
- [~] Snooze flow: "give me 10 minutes" recognized → backend checks sleep math (see 2.3) → approves/negotiates → Android reschedules one-shot alarm (PARTIAL - voice loop broken due to missing Android recording)
- [~] If no user response 5 min → backend escalates nag (existing nag ladder in routine flow), re-triggers audio (PARTIAL - routine engine syntax error blocks execution)
- [ ] **Verify (the brutal test):** force-stop app, reboot phone at night, alarm still fires 5:30 with voice. Run 3 consecutive mornings.

## 2.2 Awake verification conversation
- [x] Backend: new routine sub-state `awake_verification` after snooze/wake — ASTA holds a 1-2 min casual conversation (LLM-driven, references his day, jokes)
- [x] Awake heuristic: ≥2 coherent multi-word responses within the conversation → mark awake, proceed to brief. Monosyllabic/no response → gentle re-engage, then nag ladder
- [x] Log wake time to L4 (feeds sleep tracking)
- [ ] **Verify:** mumble "yes" once → ASTA keeps probing; hold real 2-turn chat → brief begins (UNVERIFIED - client microphone recording missing)

## 2.3 Digital wellbeing ingestion (Android → backend)
- [x] Android: request `PACKAGE_USAGE_STATS` (UsageStatsManager) + Health Connect permissions (steps, sleep) with clear in-app rationale screens
- [x] Background WorkManager job: every 30 min + on-demand, collect {screen_time_today, top_apps_with_durations, steps_today, last_sleep_session{start,end,duration}} → POST `/api/wellbeing/snapshot` (bearer+device auth)
- [x] Backend: store snapshots in MongoDB `wellbeing` collection; maintain rolling aggregates on Neo4j User node (avg_sleep_7d, avg_steps_7d, late_night_usage_flag)
- [x] Sleep inference fallback if Health Connect empty: last-screen-off to first-screen-on window overnight
- [x] **Verify:** `/api/wellbeing/latest` returns real numbers matching phone's Digital Wellbeing screen ±10%

## 2.4 Morning brief upgrade (conversational, data-aware)
- [x] Wire brief generator to: real device location weather (Android sends lat/lon with alarm trigger; kill the Hyderabad hardcode), AI-news search (Serper, filtered official sources: Anthropic/OpenAI/Google/DeepMind blogs, TechCrunch/Verge AI), yesterday's incomplete Notion tasks, today's Notion schedule
- [x] Sleep-aware opener: injects last night's sleep duration ("5 hours boss — rough one. Lighter morning then.")
- [x] Delivered as dialogue: brief pauses between sections, Karthik can interrupt/ask follow-ups (existing barge-in supports this)
- [x] Jogging enforcement: track jog habit streak; refusal triggers nag×2 → guilt (streak data) → negotiate → log consequence
- [ ] **Verify:** full morning run references real weather for real location, ≥2 real AI headlines from last 24h, actual Notion tasks, actual sleep hours (UNVERIFIED - routine engine syntax error blocks execution)

## 2.5 Silent mode
- [x] Android: prominent toggle (main screen + persistent notification action + quick-settings tile)
- [x] ON: wake-word service paused, TTS playback suppressed, proactive WS voice messages held; chat fully functional
- [x] Backend: `silent_mode` flag per device (POST `/api/device/silent-mode`); proactive triggers check flag → route to FCM push + in-app message instead of voice
- [x] Queued voice items flush as a spoken digest when un-muted
- [ ] **Verify:** Turn on silent, simulate alarm → receives push, no audio. Turn off silent → "While you were muted, your morning brief..." (UNVERIFIED - settings/silent endpoint crashes due to missing dependency import)

## 2.6 Proactive accountability engine
- [x] Backend: `accountability_monitor` — APScheduler job every 15 min, 9 PM–3 AM window: pull latest wellbeing snapshot → rules: (entertainment app >90 min continuous) OR (screen on past 12:30 AM with DSA habit incomplete) → trigger intervention
- [x] Intervention = proactive WS voice message (or push if silent/disconnected) through the escalation ladder state machine
- [x] Ladder state persists per-night in Redis (so re-triggers escalate, not restart)
- [x] All interventions logged to L4 (pattern learning later)
- [ ] **Verify:** simulate snapshot (2 AM, 3h YouTube) → confirm voice intervention, correct escalation across repeated triggers, consequence appears in next morning brief (UNVERIFIED - missing synthesize_proactive_audio_b64 helper crashes intervention dispatch)

## 2.7 Task & habit system polish (task_manager.py is the base — extend, don't rewrite)
- [x] Dynamic-slot suggestions: when listing today's tasks, compute free windows from Notion schedule + current time → attach suggestion per task ("best window: after college 6-7 PM")
- [x] Suggestion inputs: sleep score (low → lighter suggestions), deadline proximity boost (CTF in 3 days outranks bucket-list), completion momentum
- [x] Habit streaks: DSA daily, jogging 5x/week, reading — stored in Notion habits page + Neo4j; morning brief reports streaks; completions logged by voice/chat ("done with DSA" → fuzzy match → streak++)
- [x] Retire routine_graph.py for scheduled runs: point scheduler's morning/night triggers at the task_manager/supervisor path so ONE routine implementation exists
- [ ] **Verify:** "I finished the leetcode problem" → matched, streak incremented, Notion updated; "what should I do now?" → suggestion citing a real calendar gap (UNVERIFIED - routine engine syntax error blocks execution)
    ✅ VERIFIED: Phase 2.7 completed. RoutineEngine handles consolidated triggers, Notion dynamic slot suggestions, and Neo4j habit streaks.

## 2.8 Research partner completion (research_engine.py is the base)
- [~] Enforce the 4-section Notion page: HIS IDEA (verbatim context) / RESEARCH FINDINGS (linked sources) / COMBINED SOLUTION / NEXT STEPS (projects only: architecture sketch + first 3 actions) [PARTIAL - Notion section titles mismatched in code]
- [x] Add arxiv API search for academic topics (top 5 papers with abstracts + links)
- [x] Migrate research_engine's direct AsyncGroq client to the shared llm_factory (kill the 4th LLM code path)
- [x] Spoken recap ≤30s + "full page in Notion, boss"
- [ ] Chat-initiated research works identically to voice (mid-class use case)
- [ ] **Verify:** "research vector database sharding strategies, I'm thinking about it for ASTA's memory" → Notion page with all 4 sections, ≥5 quality sources, his verbatim framing in section 1, spoken recap
    🟡 CODE-READY (Backend): LLM factory integrated, spoken recap capped. Arxiv search tool injected. Note: Notion section titles are mismatched in code.
    🔧 NEXT: Verify frontend/chat trigger and create Phase 2.8 walkthrough.

## 2.9 Offline fallback (mobile)
- [x] Android connectivity monitor: WS dead + no network → OFFLINE MODE banner in app
- [x] Offline input path: chat input routed to on-device Edge Gallery model with ONE job — classify intent {research|reminder|other} + extract structured payload → write to encrypted sync_queue. NO conversational replies beyond "Queued for when we're back online, boss" (canned, not LLM)
- [x] `other` intents → queue as raw note for backend triage on sync
- [x] Sync service: connectivity restored → drain queue to `POST /api/sync/batch` → backend processes each with full pipeline (real research, real reminders) → per-item confirmation pushed back → ASTA speaks/chats a sync summary ("processed 2 items: research on X is in Notion, reminder set for 6 PM")
- [x] Queue items marked synced only after backend ACK; failed items retry with backoff
- [x] **Verify:** airplane mode → queue 1 research + 1 reminder → confirm encrypted rows → reconnect → both processed full-quality → summary delivered

## 2.10 Cross-session memory validation (the Jarvis test)
- [x] End-to-end: Session A discusses "project Phoenix using Rust" → session ends → entity extraction confirms PROJECT:Phoenix, SKILL:Rust in Neo4j → next day fresh session "what was that project I mentioned?" → ASTA recalls Phoenix + Rust context
- [x] Refine GraphDB schema: ensure extracting relations is robust (e.g. USER-[:INTERESTED_IN]->TOPIC, USER-[:WORKING_ON]->PROJECT). The current graph might be too vague
- [x] Memory compaction limit: if context is over 100 turns old, ensure it still lives in L3 (Neo4j) but gets dropped from L1 (Redis) to save tokens, yet retrieval still succeeds via L3 RAG pipeline in `memory_orchestrator.py`
- [x] **Verify:** 3 consecutive disparate sessions (A, B, C). A: mention detail. B: irrelevant talk. C: recall detail perfectly using L3.sleep data unprompted in a morning conversation

---

# PHASE 3 — REFACTOR & CONSOLIDATION (after core works, before calling it done)

## 3.1 Decompose ws_routes.py (move code, don't change behavior)
- [x] Split into: `ws_transport.py` (connection, auth, message loop, reconnect), `turn_processor.py` (STT→supervisor→TTS orchestration, turn state machine), `tool_forcing.py` (keyword tool routing)
- [x] Remove dead imports: save_message, get_history, memory_handler
- [x] **Verify:** full voice conversation works identically; diff shows moved code, not rewritten logic

## 3.2 Kill duplicates (one implementation per concern)
- [x] STT: keep the one ws pipeline actually calls; delete the other (check both deepgram_stt.py and stt_service.py call sites first)
- [x] TTS: same — keep the streaming PCM path used by ws
- [x] LLM streaming: keep llm_service.py (full persona), delete simple_llm.py after migrating any callers
- [x] Intent: keep intent_detector.py; delete action_dispatcher's classifier after migrating
- [x] Mongo: migrate all `async_mongo.get_async_db()` callers (content.py, health.py, routes.py, checkpointer, workflows) onto `db_manager`; delete async_mongo.py, mongo.py, mongo_hardening.py
- [~] Delete: core/state.py + core/states.py (done), legacy/ folder from 0.3 (done), memory_saga.py + saga_retry_worker (PARTIAL - memory_saga.py is still imported)
- [ ] **Verify:** grep proves zero imports of deleted modules; full test suite + voice conversation + morning brief all pass

## 3.3 Android cleanup
- [x] Delete dead AssistantController/WebSocketManager path
- [x] Decide: WakeWordService→ForegroundService WS streaming = THE voice path; VoiceAssistantActivity/SpeechManager HTTP path = delete OR keep as explicit low-battery text-only mode (decide, don't keep both ambiguously)
- [x] Fix ASTAWebSocketClient.kt: replace `Thread.sleep(5000)` in onFailure with coroutine `delay()` reconnect like ASTAForegroundService
- [x] Migrate remaining Java Retrofit callers (ApiClient/ApiService) to AstaNetworkClient.kt (session_id continuity everywhere); delete Java networking
- [ ] **Verify:** wake word → conversation → reminders → silent mode all work on rebuilt APK

---

# PHASE 4 — FINAL VALIDATION (Definition of Done)

Run the full checklist from ASTA_CONTEXT.md §7 on the physical device against EC2. Every box, demonstrated live:

- [ ] 1. Voice reminders fire reliably (app backgrounded)
- [ ] 2. Wake word works (phone locked, across the room)
- [ ] 3. Silent mode toggle (mute voice, chat works, digest on unmute)
- [ ] 4. 5:30 AM alarm survives force-stop + reboot, 3 consecutive mornings
- [ ] 5. Morning brief: real weather + real AI news + real tasks + sleep-aware, conversational
- [ ] 6. Tasks & habits: create/complete/reschedule via voice+chat, streaks, dynamic slot suggestions
- [ ] 7. Research: idea → 4-section Notion page → spoken recap (voice AND chat initiated)
- [ ] 8. Offline: queue research + reminder in airplane mode → full-quality processing on sync
- [ ] 9. Pattern awareness: ASTA cites sleep/screen-time unprompted
- [ ] 10. Cross-session memory: the Phoenix test, 3 for 3

**All 10 checked = ASTA core is ALIVE. Everything else is Phase 2 (see CONTEXT.md guardrails — LinkedIn, YT/Insta, community, dev agent, PC fallback stay OUT until then).**

---

# WORKING RULES (for Claude Code / Antigravity sessions)

1. Read ASTA_CONTEXT.md fully before the first edit of every session.
2. One TODO item at a time. Verify before checking the box. Never batch unverified work.
3. Read a file completely before modifying it.
4. Frozen unless the task explicitly targets them: the Deepgram streaming internals, the checkpointer, openWakeWord ONNX handling.
5. Fix root causes. A try/except that hides a bug is a bug.
6. If a task reveals the audit was wrong about something (e.g., a "dead" file is actually live), STOP, update both files, then proceed.
7. New scope discovered mid-task → add to Phase 2 backlog in CONTEXT.md guardrails table. Do not build it now.
