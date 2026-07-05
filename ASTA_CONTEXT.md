# ASTA_CONTEXT.md
> **The single source of truth for what ASTA is, how it works, and what NOT to build.**
> Read this ENTIRE file before writing any code. Every decision traces back to this document.
> Owner: Karthik. Single user. Forever.

---

# 1. WHAT ASTA IS

ASTA is Karthik's Jarvis. Not a chatbot. Not an app. A persistent, proactive, always-on second brain that:

- **Wakes him up** at 5:30 AM and verifies he's actually awake through conversation
- **Briefs him** — weather, AI news, yesterday's incomplete tasks, today's schedule
- **Manages his chaos** — college + startup + internship + community (300 students) + DSA + 10 bucket-list projects + hackathons + CTFs
- **Researches for him** — he drops a half-formed idea mid-class, ASTA researches it deep and organizes it in Notion
- **Fights his bad habits** — sees the 2 AM anime binge via screen-time data, nags twice, then guilts/negotiates/applies consequences
- **Learns his patterns** — passive observation (sleep, steps, app usage, conversation tone), never needs to be told how he feels
- **Never dies** — offline fallback queues tasks locally, syncs when back online

## The Jarvis Standard
Tony Stark never explained himself to Jarvis. Jarvis observed, inferred, acted, and spoke up when it mattered. That is the bar. ASTA should know Karthik slept 4 hours before Karthik mentions being tired.

## Personality
- Gen-Z, cheerful, funny, occasionally sarcastic. Calls him "boss".
- Shifts to professional/focused mode during research and deep work.
- Persistent but not annoying: nag maximum 2 times, then switch strategy (guilt → negotiate → consequences).
- Voice responses: 1-3 sentences unless detail requested. Never robotic.

---

# 2. CURRENT SYSTEM STATE (build ON TOP of this — do not rebuild)

## What EXISTS and WORKS (verified by audit)
- FastAPI backend on EC2, exposed via ngrok systemd service
- LangGraph supervisor graph (`core/supervisor_graph.py`, 558 lines): classify_intent → route → {routine|research|content|other} → save_session
- 4-layer memory: Redis (L1) → Neo4j (L2) → Pinecone (L3, 384-dim MiniLM) → MongoDB (L4), orchestrated by `memory/memory_engine.py`
- Voice pipeline end-to-end: openWakeWord ONNX on-device → WS PCM streaming → Deepgram STT → supervisor → Deepgram TTS → PCM back
- AsyncMongoDBSaver checkpointer (fixed) — enables interrupt()-based multi-turn clarification
- Scheduler: morning alarm 5:30 AM IST + night planning 10:30 PM IST via APScheduler
- FCM push notifications (deployed and verified)
- task_manager.py: conversational task engine with rapidfuzz matching + interrupt() clarification
- research_engine.py: Serper search + scraping + Notion save
- notion_service.py: 572 lines, full CRUD for tasks/routines/gratitude/content/habits
- Android app: Kotlin + Flutter UI, wake word bundled in APK, FCM integrated

## KNOWN CRITICAL BUGS (fix FIRST, before any new features)
1. **L1.5 speculative prefetch has NEVER worked**: `memory_orchestrator.py` calls `set_speculative_data(key=, data=, ttl=10, trigger_query=)` but actual signature is `set_speculative_data(self, key, value, ttl=300)`. TypeError swallowed by broad except. Fix the kwargs mismatch.
2. **SessionManager calls ghost methods**: `CacheService.set_session_cache()`/`get_session_cache()` don't exist — only `get_json/set_json/delete_session_cache` exist. Incomplete refactor. Add the missing methods or migrate calls.
3. **Two Neo4j schemas corrupting one Aura instance**: `l2_graph.py` (User→HAS→Entity, current) vs `graph_service.py` (Person→Category→SkillGroup→Skill, legacy, aliased confusingly as `l3_manager`). Migrate call sites to l2_graph.py, retire graph_service.py.

## KNOWN CLEANUP TARGETS (do during build, not before)
- `ws_routes.py` is a 1,408-line god file → split into ws_transport.py / turn_processor.py / tool_forcing.py
- Two Motor pools to same MongoDB (`database.py` db_manager vs `async_mongo.py`) → consolidate onto db_manager
- Dead files: `db/mongo.py` (271 lines, zero imports), `auth/middleware.py` (dead JWT track), `core/state.py` vs `core/states.py` collision (neither used by live graph)
- Dead imports in ws_routes.py: save_message/get_history/memory_handler — remove
- Duplicated STT/TTS/LLM implementations (deepgram_stt vs stt_service, deepgram_tts vs tts_service, llm_service vs simple_llm) → keep ONE of each, delete the other
- Two intent classifiers (action_dispatcher: identity/action/knowledge/chitchat vs intent_detector: casual/tool/memory/general) → keep intent_detector, align labels with supervisor
- Android: delete dead AssistantController/WebSocketManager path; keep WakeWordService→ASTAForegroundService streaming path as THE voice architecture
- Mobile: `ASTAWebSocketClient.kt` onFailure uses blocking Thread.sleep(5000) → replace with coroutine delay() like ASTAForegroundService does
- `weather_service.py` hardcoded city → wire to device location from Android
- Pin `groq` in requirements.txt (currently transitive via langchain-groq)
- Verify `TaskRegistry.shutdown()` exists (main.py calls it; audit couldn't find the method)
- memory_saga.py legacy pipeline runs alongside memory_engine → retire saga after confirming memory_engine handles all writes

---

# 3. TECH STACK (confirmed, do not deviate)

| Layer | Technology | Notes |
|---|---|---|
| Backend | FastAPI (Python 3.11) | Existing, keep |
| Orchestration | LangGraph + AsyncMongoDBSaver checkpointer | thread_id = session_id |
| LLM primary | Groq (llama-3.3-70b-versatile fast, llama-3.1-8b-instant cheap) | Pin groq in requirements |
| LLM fallback | Gemini (gemini-1.5-flash) | Auto-fallback on 429 |
| LLM deep writing | Claude (via Anthropic API) | Research synthesis, scripts |
| STT/TTS | Deepgram (nova-2 STT, aura male American TTS) | Streaming both ways |
| Wake word | openWakeWord ONNX, on-device | Already bundled in APK |
| Search | Serper API + BeautifulSoup scraping | ~40 domain allowlist |
| Memory L1 | Redis | Hot cache, degrades to no-op |
| Memory L2 | Neo4j Aura | Knowledge graph — ONE schema only (l2_graph.py) |
| Memory L3 | Pinecone serverless | 384-dim MiniLM embeddings |
| Memory L4 | MongoDB Atlas | Cold store, 90-day transcript TTL |
| Output | Notion API | Research pages, tasks, habits, gratitude |
| Push | FCM (firebase-admin) | Deployed and working |
| Mobile | Android Kotlin + embedded Flutter UI | Existing app, extend |
| Mobile offline LLM | Edge Gallery local model (~4GB) on phone; DeepSeek-Coder 7B on PC | Fallback only, task-queueing not conversation |
| Local offline DB | SQLite (mobile) with SQLCipher encryption | Sync queue |
| Deployment | EC2 + ngrok systemd (current) → static ngrok domain or open port 8000 | ngrok URL changes on EC2 reboot = app rebuild; fix this |
| Scheduler | APScheduler (Asia/Kolkata timezone) | 5:30 AM + 10:30 PM crons exist |

---

# 4. THE CORE FEATURES (Phase 1 — the next 10 days)

## 4.1 Morning Wake-Up Flow (the flagship feature)
```
5:30 AM IST — AlarmManager full-screen intent fires (works even if app killed / phone rebooted)
    ↓
ASTA speaks wake-up message (energetic, personal, references his day)
    ↓
Karthik responds OR silence
    ↓ silence 5 min → nag (escalating: gentle → firm → guilt)
    ↓ "give me 10 more minutes" → ASTA checks sleep math:
        - If ≥6 hours slept → negotiates ONE snooze, re-fires
        - If <6 hours → allows but flags it for tonight's planning
    ↓
AWAKE VERIFICATION: not "say yes" — a real 1-2 minute conversation
(jokes, how'd you sleep, random chat — ASTA confirms coherent responses = actually awake)
    ↓
MORNING BRIEF (conversational, not a data dump):
    1. Weather (device location, not hardcoded)
    2. AI news (Anthropic/OpenAI/Google breakthroughs, filtered official sources)
    3. Yesterday's incomplete tasks ("you didn't finish X — moving to today")
    4. Today's schedule (meetings, college, non-negotiable tasks)
    ↓
JOGGING ENFORCEMENT: goal = 5 days/week. If he refuses, ASTA pushes back with streak data.
Persistence: nag 2x max, then guilt → negotiate → consequence (log the skip, adjust weekly stats)
```

## 4.2 Task & Habit System
- **Non-negotiable tasks, dynamic time slots.** ASTA never says "DSA at 4:30 PM". It says "DSA must happen today — best window looks like after college, 6-7 PM, you have nothing then."
- Suggestions factor in: energy (sleep data), calendar gaps, momentum (what he's done today), deadline pressure (CTF in 3 days > bucket-list project)
- Habit tracker: DSA daily, jogging 5x/week, reading — streaks tracked, broken streaks called out in morning brief
- Task creation via voice or chat: LLM extracts task/time/priority; missing time → interrupt() asks; reminder scheduled via APScheduler → fires as WS voice message + FCM push
- Task completion: fuzzy-match spoken name against today's Notion tasks (rapidfuzz WRatio ≥60, must beat runner-up by 20 or disambiguate) — THIS EXISTS in task_manager.py, keep it

## 4.3 Research Partner (the second flagship)
Trigger: Karthik says/types "research X" — often mid-class via chat.
```
1. Capture his raw idea/context FIRST (what he said, his angle, why he cares)
2. If offline → queue locally, process on sync
3. Research: Serper multi-query fan-out (LLM generates 3 subqueries) → scrape allowlisted domains → arxiv for papers → top 5 papers if academic
4. Create Notion page under Research DB:
   Section 1: HIS IDEA — verbatim context he gave, his thinking
   Section 2: RESEARCH FINDINGS — top resources, papers, key points with links
   Section 3: COMBINED SOLUTION — synthesis of his angle + findings
   Section 4 (if project): NEXT STEPS — architecture sketch, base build plan, first 3 actions
5. Voice/chat recap: 30-second spoken summary + "full page in Notion, boss"
```
Quality bar: only official docs, papers, verified sources. Zero SEO spam, zero Reddit.

## 4.4 Silent Mode (meetings/class)
- Toggle in app: ASTA goes mute — no voice, no proactive speech, wake word paused
- Chat remains fully functional (chat is a primary interface, not a fallback)
- Voice reminders queue while muted, deliver as FCM push + in-app instead
- Auto-suggestion (Phase 2): detect calendar meeting → suggest going silent

## 4.5 Proactive Accountability
- Data ingested passively from Android: UsageStatsManager (screen time, per-app usage), Health Connect (steps, sleep), wake/sleep hours
- Pattern detection: "2 AM, third episode of anime, DSA not done" → ASTA speaks up proactively
- Escalation ladder (hard rule): nag ×2 → guilt (reference HIS stated goals) → negotiate ("one more episode then sleep — deal?") → consequence (tomorrow's brief opens with the damage: "4 hours sleep, streak broken, today's plan is lighter")
- ASTA NEVER silently adjusts. It always tells him what it saw and what it's doing about it.

## 4.6 Offline Fallback (quality is non-negotiable)
- **NO conversations with local model.** Local models are dumber; Karthik refuses degraded chat quality.
- Local model's ONLY job: parse intent from input → create structured task entries in encrypted local queue
- Queueable offline: research requests (topic + his context), reminders (content + time)
- On reconnect: sync queue → backend processes each with FULL power (real research, real reminder creation) → confirms to Karthik what was processed
- Same architecture on PC (DeepSeek-Coder 7B) — Phase 2, mobile first
- Local storage: SQLite + SQLCipher, key in Android Keystore

## 4.7 Memory & Learning (the Jarvis brain)
- Every session → entity extraction (PROJECT/SKILL/PERSON/GOAL/TOPIC/DECISION/TASK) → L4 write (durable, sync) → L3+L2 parallel (isolated failures) → L1 invalidation
- Retrieval: entity spotting (pure string match, no LLM) → L1 cache → L2 cluster → L3 scoped vector search → L4 fetch → fallback unscoped L3
- L1.5 prefetch (once fixed): entity mentioned mid-sentence → background warm of L1 before the turn needs it
- Pattern learning (Phase 1 basics): sleep patterns, app usage patterns, task completion times → stored as User node properties in Neo4j (current_focus, avg_sleep, productive_hours)
- Deep pattern intelligence (knowledge-graph growth suggestions, weekly reviews) → Phase 2

---

# 5. SECURITY MODEL (Phase 1, non-negotiable)

- **Single user. Forever. No multi-tenancy code, no user tables, no registration.**
- Auth: static bearer token via `hmac.compare_digest` (the existing routes.py mechanism) — consolidate to ONE shared module, delete the duplicate in main.py and the dead auth/middleware.py
- **Device binding**: Android app generates device ID on first launch → registered with backend → backend rejects any request with valid token but unknown device ID. Two-factor: token + device.
- Token storage: Android Keystore (hardware-backed), never plaintext
- Local offline DB: SQLCipher encryption, key in Keystore
- WebSocket auth: token in query param (Android WS header limits), validated before accept, close 1008 on failure
- No auth bypass: remove the silent no-op when API_KEY unset — Phase 1 REQUIRES the token, log a fatal warning if unset
- ngrok/domain: current ngrok URL is in the APK. Fix: static ngrok domain OR proper port 8000 + Elastic IP + domain, so EC2 reboots don't require app rebuilds

---

# 6. GUARDRAILS — WHAT NOT TO BUILD (Phase 1 discipline)

These are explicitly DEFERRED. Do not write code for them. Do not scaffold them. Do not "prepare" for them.

| Deferred Feature | Why | Phase |
|---|---|---|
| LinkedIn post generation | Karthik has a separate existing project; will plug in later | 2 |
| YouTube/Instagram research & scripts | Wants it, but core first | 2 |
| Community automation (n8n, 200-site scraper, WhatsApp) | Separate system, ASTA only triggers it later | 2 |
| Developer agent | Explicitly "later" | 2 |
| PC fallback (DeepSeek 7B) | Mobile offline fallback first | 2 |
| Weekly reviews / growth suggestions / knowledge-graph learning paths | Jarvis-level intelligence, iterate after core | 2 |
| Watch integration | "Very later" | 3 |
| Meeting auto-detect for silent mode | Manual toggle is Phase 1 | 2 |
| Multi-model routing beyond Groq/Gemini/Claude | Current trio is enough | 2 |

## Engineering guardrails
- **DO NOT rewrite the voice pipeline.** It works. ws_routes decomposition is refactoring (moving code), not rewriting (changing behavior).
- **DO NOT create new parallel implementations.** The codebase died a little from 3 generations of duplicated STT/TTS/LLM/networking. One implementation per concern. Delete the losers.
- **DO NOT add try/except to silence errors.** The L1.5 prefetch bug survived because a broad except ate a TypeError for months. Every except must log with context and have a reason to exist.
- **DO NOT touch the working checkpointer** (AsyncMongoDBSaver 0.4.0) — it was just fixed.
- **DO NOT store secrets in code or APK beyond the base URL.** Token flows through Keystore.
- **Write order in memory is sacred**: L4 first (durable) → L3+L2 parallel → L1 invalidate. Layer failures are independent — L2 down never rolls back L4.
- **Fail-soft startup stays**: only env validation is fatal; every other layer degrades and reports via StatusRegistry.

---

# 7. THE DEFINITION OF DONE (Phase 1 checklist)

ASTA core is DONE when ALL of these work flawlessly, demonstrated end-to-end on the physical Android device against the EC2 backend:

1. ☐ **Voice reminders fire reliably** — created by voice/chat, delivered at the right time as spoken WS message + FCM push, even with app backgrounded
2. ☐ **Wake word works** — "hey Jarvis" from across the room, phone locked, triggers conversation
3. ☐ **Silent mode toggle** — one tap mutes all voice/proactive output; chat still fully works; un-mute restores
4. ☐ **5:30 AM wake-up survives everything** — app killed, phone rebooted overnight, still fires full-screen with voice; snooze negotiation works; awake-verification conversation works
5. ☐ **Morning brief is conversational** — weather (real location) + AI news + yesterday's incompletes + today's schedule, delivered as dialogue not monologue
6. ☐ **Task & habit management** — create/complete/reschedule by voice or chat, fuzzy matching works, streaks tracked, dynamic time-slot suggestions reference his real calendar gaps
7. ☐ **Research partner full loop** — idea in (voice or chat, even offline-queued) → Notion page out with all 4 sections (his idea / findings / synthesis / next steps) → spoken recap
8. ☐ **Offline fallback** — airplane mode → queue a research topic + a reminder → reconnect → both processed with full quality → ASTA confirms
9. ☐ **Pattern awareness v1** — ASTA references his sleep hours and screen time in conversation without being told ("you slept 5 hours boss, taking it easy on the morning schedule")
10. ☐ **Memory works across sessions** — discuss project X today, ask about it in a fresh session tomorrow, ASTA recalls the context

Anything not on this list that appears in the codebase during Phase 1 is scope creep. Kill it.

---

# 8. NORTH STAR

Karthik is ambitious but careless sometimes. Watches anime all night, forgets project ideas from class, loses track of ten parallel commitments. ASTA exists because he asked for someone in his corner at 2 AM saying "put it down, boss — you told me DSA matters to you."

Every feature decision: **does this make ASTA a better Jarvis for THIS person's actual life?** Not a general assistant. Not a product for users. One person's second brain, built to know him better than he knows himself on his worst days.

Six months of create → optimize → delete → optimize. But the core lives in 10 days.
