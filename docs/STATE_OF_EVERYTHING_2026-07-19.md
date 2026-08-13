# ASTA — State of Everything
**Audit date:** 2026-07-19 · **Branch:** `face-and-soul` (both repos, in sync with `origin`, 0 ahead/0 behind) · **Auditor mode:** read-only reconnaissance, live probes only where explicitly evidenced.

Every claim below carries a `file:line`, a pasted command output, or a git SHA. Where I could not determine something, it says `UNKNOWN — because <reason>` rather than guessing.

---

## THE HEADLINE

**ASTA does NOT currently remember on its own.** The extraction pipeline built two days ago (commits `d12f6551`, `edf79ca9`) is real, substantive code — not a stub — but it has never once fired successfully: the `insights` collection in MongoDB has **zero documents**, ever, across **230 recorded sessions**. I ran the exact live end-to-end probe (`scripts/prove_memory_loop.py`) the previous agent wrote but never actually executed (its own `docs/CLOSE_THE_LOOP_REPORT.md` admits "Live run was not completed in this session"). It failed: the FastAPI WebSocket handler never reaches its cleanup code after a client disconnects, so `enqueue_extraction()` is never called, so the outbox worker never has anything to process. This is evidenced live, with timestamps, below (§C4).

Three other truths a busy Karthik needs before reading further:

1. **There are two separate, uncoordinated memory systems** wired into the same backend, writing to the same MongoDB database, sometimes the same collection name, with three incompatible document schemas. The voice WebSocket path (what the frontend/mobile actually use) writes to `insights` + a Graphiti/Neo4j client (`backend/app/services/memory/*`). The text-chat HTTP path (`/api/chat`, used by `supervisor_graph`/`session_manager`) writes to a completely different `memory_engine` L1–L4 stack (`memory/*`). A fact told to ASTA by voice is invisible to the text-chat path and vice versa. This mixing is directly responsible for a real boot-time error (`Failed to restore active sessions: Document requires 'messages' field`) — evidenced live in §C1/§H1.
2. **Neo4j Aura — the graph layer both memory systems depend on — is completely unreachable right now**, from this machine *and* from the currently-live deployed AWS server: `Failed to DNS resolve address 34e6ab76.databases.neo4j.io:7687`. This almost certainly means the free-tier Aura instance has been paused or deleted, not a local network issue (confirmed on two independent hosts). Every health endpoint reports it as healthy anyway, because the health-check code hardcodes `"l2_neo4j": True` regardless of actual connectivity (§B5/§D2).
3. **A backend IS live in production right now** at the AWS host baked into the mobile app's default config, answering real requests — but it is running older, pre-memory-fix code and reports every one of its memory backends (Mongo, Neo4j, Redis, Pinecone) as down (`"memory_mode":"local_only"`). Nothing has been deployed since before this loop of work started (§G2).

---

## MASTER TABLE

| Subsystem | Status | Evidence pointer |
|---|---|---|
| Backend boots (import + `/api/health/`) | ✅ VERIFIED-LIVE | §D2, cold boot log |
| `make verify` (import → boot → pytest) | ❌ BROKEN | §D1 — 6 failed / 47 passed |
| Voice WS pipeline (`/ws/conversation`) end-to-end reply | ✅ VERIFIED-LIVE | §C4, §D5 — real Groq reply received |
| Automatic memory extraction (voice path) | ❌ BROKEN | §C4 — 230 sessions, 0 insights, ever |
| Memory recall (voice path, semantic) | 🟡 WIRED-UNPROVEN | §C2 — code real, never exercised successfully because nothing is ever stored |
| Text-chat memory (`/api/chat` → `memory_engine`) | 🟡 WIRED-UNPROVEN | §C1 — separate system, not live-probed this session |
| Private mode (voice path) | 🟡 WIRED-UNPROVEN | §C3 — enforced in code, not exercised live (no insights ever written to compare against) |
| Neo4j Aura (both memory systems' L2) | ❌ BROKEN | §D2/§G3 — DNS resolution fails from 2 independent hosts |
| MongoDB Atlas | ✅ VERIFIED-LIVE | §D2/§G3 — connects, 230+ sessions present |
| Pinecone | ✅ VERIFIED-LIVE | §D2 — connects, index stats logged |
| Redis (local) | ✅ VERIFIED-LIVE | §D2 |
| Scheduler (APScheduler, 9 jobs) | ✅ VERIFIED-LIVE | §B2 — registered at boot; reminder job fired live |
| Reminder delivery pipeline | ✅ VERIFIED-LIVE | §D4 — scheduled → fired → state transition proven live |
| LLM routing (Groq primary) | ✅ VERIFIED-LIVE | §D5 — real completion, 200 OK from api.groq.com |
| `research_service.py` / "look into X" voice intent | ❌ BROKEN | §H2 — `ModuleNotFoundError`, confirmed via direct import |
| 6 `*_graph.py` LangGraph workflow modules | ⚠️ SCAFFOLD | §B4 — zero importers, confirmed dead |
| Frontend dev server | ✅ VERIFIED-LIVE | §E — served, 200 OK |
| Frontend ↔ live backend WS protocol | ❌ BROKEN | §E — frontend has no handler for what the backend actually sends |
| Deployed AWS backend | ✅ VERIFIED-LIVE (stale code, degraded memory) | §G2 |
| CI (`.github/workflows/ci.yml`) | ⚠️ SCAFFOLD (wrong branch) | §G5 — triggers only on `master`, all recent work is on `face-and-soul` |
| Mobile — wake word | 🟡 WIRED-UNPROVEN, mislabeled | §F — ships "hey_jarvis.onnx" while all UI text claims "Hey ASTA" |
| Mobile — build | ❌ BROKEN | §F — Gradle config-time Kotlin-DSL error, reproduced twice |
| Mobile — boot persistence / Doze exemption | ⬜ MISSING | §F — `BootReceiver` only reschedules the alarm; no battery-exemption request anywhere |
| Mobile — bearer token in git history | ❌ CRITICAL, unrotated risk | §F — plaintext token recoverable from 3 pushed ancestor commits despite a real code-level fix in HEAD |

---

## PHASE A — REPO CENSUS

### A1–A2. Remotes, branches, status

**Main repo** (`Asta`, this checkout): remote `origin` → `https://github.com/KARTHIK-BATTIPROLU/Asta.git`. Current branch `face-and-soul`, clean (`git status --porcelain` empty), **0 ahead / 0 behind `origin/face-and-soul`**. Branches with dates:
```
face-and-soul 2026-07-17          origin/face-and-soul 2026-07-17
v0.2-face-soul 2026-07-16         ship-ready 2026-07-16 / origin/ship-ready 2026-07-16
verification-audit 2026-07-16     phase-2-wakeword 2026-07-13 / origin/phase-2-wakeword
master 2026-07-10                 phase-1-voice 2026-07-10
phase-0-stabilize 2026-07-10      attic 2026-07-10
origin 2026-07-07                 origin/master 2026-07-07
v0.1-engine, v0.1-functional (no dates — old annotated tags)
```
**No uncommitted or unpushed work** — everything is on `origin`.

**Mobile repo** (`ASTA MOBILE`, submodule → `ASTA_APP`): remote `origin` → `https://github.com/KARTHIK-BATTIPROLU/ASTA_APP.git`. Branch `master`, clean, **0 ahead/behind `origin/master`**.

### A3. Last 10 commits, diffs read (not messages) — main repo

| SHA | Message | What the diff actually shows |
|---|---|---|
| `bae2d5d3` | loop-M8 report | 2-line edit to an existing doc, gate-table wording only |
| `a56f3bcc` | RUN_ME_KARTHIK + test fixes | Adds `docs/RUN_ME_KARTHIK.md`, `docs/CLOSE_THE_LOOP_REPORT.md` (178 lines, contains the prior agent's own admission the live probe never ran), tweaks `test_wakeword_parity.py` and `test_outbox_wiring.py` |
| `c601e500` | wake word config, dead route cleanup | **Deletes** `health_routes.py` (43 lines) and `metrics_routes.py` (78 lines) outright, plus 17 lines from `deepgram_client.py`; edits `wakeword_processor.py` |
| `edf79ca9` | prove_memory_loop + pipeline | Adds `scripts/prove_memory_loop.py` (285 new lines) and 21 lines to `pipeline.py` — this is the script I ran live in §C4 |
| `d12f6551` | outbox wiring | Real new code: `services/memory/outbox.py` (47 new lines), `voice/session_store.py` (98 new lines), edits to `ws_transport.py`, `outbox_worker.py`, `main.py`, `extractor.py`, plus a 156-line new test file |
| `d81d8294` | ASTA rebrand | Renames `JarvisOrb.tsx`→`AstaOrb.tsx` (97% similarity — cosmetic), edits `persona.py`, `App.jsx` (+92 lines: browser wake word) |
| `69b061b1` | submodule bump | 1-line pointer update only |
| `e06149d0` | wake word + persona | Edits (not additions) to `persona.py` and `wakeword_processor.py`, -31 net lines |
| `fe7ff223` | UI revert | **Removes 510 lines** from `App.css`/`App.jsx`, adds 53 to `JarvisOrb.tsx` — a rollback, not new work |
| `067ab5d7` | crash fix | 24-line fix moving `ASTA_PARAMS` above the render loop in `orbScene.ts` |

### A3. Last commits — mobile repo (all real diffs, not just messages)

| SHA | Message | Diff reality |
|---|---|---|
| `d43594d` | move bearer token to local.properties | Real: token literal removed from tracked `.kt` files, `BuildConfig` field added reading from `local.properties` |
| `298cf80` | wake word service, audio streaming | Substantive new Kotlin service files (see §F) |
| `bb7910d` | purge ngrok fallbacks | `BuildConfig.SERVER_URL` used instead of hardcoded ngrok |
| `bd55827` | AWS backend wiring | This is where `[AWS-host-redacted]` was introduced |

### A4. Submodule sync
`git ls-tree HEAD "ASTA MOBILE"` → `d43594d34f38647a4ceac00aade5e71f3b881494`. `git -C "ASTA MOBILE" rev-parse HEAD` → same SHA. **In sync.**

### A5. Size census (tracked files only, main repo)
Top file types: 242 `.json`, 185 `.py`, 22 `.md`, 8 `.js`, 7 `.txt`/`.sh`. Top-level dirs by file count: `graphify-out/` (235 — a prior graphify run's output, committed; **UNCLEAR-PURPOSE / should probably be gitignored, not tracked**), `backend/` (133), `frontend/` (26), `docs/` (25), `memory/` (21 — the *other* memory system, see §C1), `notion_tests/` (18), `scripts/`/`ops/` (4 each), `tests/`/`deploy/` (3 each), `clients/` (2, UNKNOWN-PURPOSE — not inspected this pass), `.kiro/` (4, UNKNOWN-PURPOSE — appears to be an IDE-specific config dir, not inspected).

Mobile repo: 32 `.kt`, 26 `.xml`, 13 `.java` (a legacy pre-Kotlin layer, still present alongside Kotlin), 3 `.onnx` (wake-word models), 3 `.kts` (Gradle build scripts).

---

## PHASE B — THE WIRING MAP

### B1. `backend/app/main.py` — the living system

Routers mounted (`main.py:75-86`): `ws_router` (no prefix — `/ws/conversation`), `api_router`→`/api` (`routes.py`), `preferences_router`→`/api`, `content_router`→`/api`, `health_router`→`/api` (has its **own** internal `/health` prefix, so lands at `/api/health/`), `settings_routes.router`→`/api`, `sync_routes.router`→`/api/v1`.

Startup sequence (`main.py:216-481`, each step try/except-wrapped so one failure doesn't stop boot): env validation (fail-fast — kills boot if core libs missing) → spaCy model check (degrades) → Mongo connect + Neo4j Aura ping (degrades) → Redis connect (degrades) → `EmbeddingService` → Pinecone vector store → `SessionManager.restore_active_sessions()` + `start_workers()` → **outbox worker** (`start_outbox_worker()`) → wake word service (openWakeWord, gated on `WAKE_WORD_ENABLED`) → tool registry → **legacy `memory_engine.connect_all()`** (the *other* memory system) → LangGraph checkpointer + compiled supervisor graph → **APScheduler start** (9 jobs, see B2) → reminder reload from Notion → seed data.

Shutdown (`main.py:484-538`): scheduler stop → memory_engine disconnect → checkpointer close → embedding service shutdown → outbox worker stop → SessionManager stop → TaskRegistry drain (3s timeout) → db disconnect → redis close. This is a real, ordered shutdown path, not a stub.

### B2. Scheduler truth (`backend/app/services/scheduler_service.py`)

All 9 jobs registered at `.start()` (lines 47-108), timezone `Asia/Kolkata`, in-memory job store (deliberately — comment at lines 21-27 explains MongoDBJobStore can't pickle the bound-method callbacks, so reminders are reconstructed from Mongo on every boot instead):

| Job ID | Schedule | Callback | Substantive? |
|---|---|---|---|
| `morning_alarm` | 05:30 daily | `_trigger_morning_alarm` → `run_supervisor_graph` + WS broadcast | Real |
| `night_planning` | 22:30 daily | same pattern | Real |
| `dead_man_check` | 05:35 daily | checks for a recent `morning_alarm` session doc; if missing, logs CRITICAL and a comment admits FCM push is **simulated** for now (`scheduler_service.py:187-188`) | Partially stubbed (logs only, no real push) |
| `habit_engine` | hourly | `habit_service.run_tick()` | Real call, not audited deeper this pass |
| `daily_recap` | 20:30 | `reflection_service.run_daily_recap()` | Real call |
| `sunday_reflection` | Sun 22:00 | `reflection_service.run_sunday_reflection()` | Real call |
| `nightly_prediction` | 01:00 | `proactive_service.run_nightly_prediction()` | Real call |
| `weekly_radar` | Sun 09:00 | `subscription_service.run_weekly_radar()` → imports `research_service` | **Will crash** — see §H2, `research_service.py` fails to import |
| `self_test` | 03:00 | checks `job_runs` collection for yesterday's expected jobs, escalates via `reminder_service` if any are missing | Real, and clever — a real self-monitoring job |

`_startup_catch_up()` (lines 118-154) also runs on every boot: finds reminders whose `due_ts` is in the past, fires ones <30min late, parks older ones. Real code.

### B3. Voice pipeline anatomy (`backend/app/voice/pipeline.py:189-218`)

Order: `transport.input()` → **[if `trigger=="wake_word"`]** `ServerWakeWordConfirmProcessor` (openWakeWord, gates all audio until a wake phrase scores ≥0.6) → `VADProcessor` (Silero) → `VadOrbNotifier` (broadcasts `orb_state:listening`) → `GroqWhisperSTT` → `ReflexProcessor` (not audited deeper this pass) → `MemoryContextInjector` (recall + system-prompt injection, see §C2) → `RouterLLMService` (routes to `llm_factory.router`, handles private-mode commands, morning-brief injection, and the broken research-intent branch) → `SentenceAggregator` → `LanguageSplitTTS` (broadcasts `orb_state:speaking/idle` + the response text, then synthesizes via edge-tts) → `transport.output()`.

Note: the *browser* frontend (§E) no longer passes `trigger=wake_word` (removed in `d81d8294`), so `ServerWakeWordConfirmProcessor` is currently dead weight for web clients — wake-word detection for the web UI is 100% the browser's Web Speech API now (§E.3).

### B4. The attic ledger

Confirmed **dead code (zero importers anywhere in the repo)**, verified by a full import-edge sweep across `backend/app/**/*.py`:

| Path | Guessed intent | Tag |
|---|---|---|
| `backend/app/workflows/habit_graph.py` | LangGraph state-machine for habit tracking | ⚠️ SCAFFOLD |
| `backend/app/workflows/instagram_graph.py` | LangGraph state-machine for Instagram content | ⚠️ SCAFFOLD |
| `backend/app/workflows/linkedin_graph.py` | LangGraph state-machine for LinkedIn content | ⚠️ SCAFFOLD |
| `backend/app/workflows/research_graph.py` | LangGraph state-machine for research | ⚠️ SCAFFOLD |
| `backend/app/workflows/routine_graph.py` | LangGraph state-machine for routines | ⚠️ SCAFFOLD |
| `backend/app/workflows/youtube_graph.py` | LangGraph state-machine for YouTube content | ⚠️ SCAFFOLD |
| `backend/app/api/turn_processor.py` (847 lines) | An older HTTP-turn-based conversation handler with its own `status`/`llm_chunk`/`audio` WS-style protocol | ⚠️ SCAFFOLD — not registered as any route, `TurnProcessor` class never instantiated anywhere (confirmed by the frontend agent); only its `fetch_memory_context` helper function is imported live by `routes.py` |
| `backend/app/api/health_routes.py`, `metrics_routes.py` | Superseded health/metrics endpoints | Already deleted in `c601e500` — no longer in the tree |
| `frontend/app.js`, `frontend/orb.js`, `frontend/style.css` | Pre-React vanilla-JS prototype | ⚠️ SCAFFOLD — unreferenced by `index.html` |
| `frontend/src/api/index.js` | Axios REST client | ⚠️ SCAFFOLD — never imported by `App.jsx`, which talks to the backend exclusively via raw WebSocket |

**Superseded-not-dead pattern:** each `*_graph.py` above has a same-topic `*_engine.py`/`*_manager.py` sibling that **is** reachable (via `action_executor.py` or `supervisor_graph.py`) — the LangGraph state-machine rewrite was apparently abandoned mid-migration in favor of simpler direct-call implementations. 6 confirmed-dead workflow files total, out of 21 in `workflows/`.

**Two memory systems living side by side** is the single largest "attic-adjacent" finding of this audit — not dead code, but two *live, both-reachable* systems that don't talk to each other. Full detail in §C1/§H1.

### B5. Config census (`backend/app/config.py`, 155 lines, ~70 declared settings)

Spot-checked 19 settings for actual runtime usage (`grep` for `settings.<KEY>` / `config.<KEY>` anywhere outside `config.py` itself): **17 of 19 are never referenced anywhere** — `RATE_LIMIT_ENABLED`, `NOISE_SUPPRESSION_ENABLED`, `REQUEST_QUEUE_MAXSIZE`, `REQUEST_QUEUE_WORKERS`, `MAX_CONCURRENT_FFMPEG`, `SESSION_TTL_DAYS`, `CLEANUP_RETENTION_DAYS`, `CLEANUP_LOW_PRIORITY_THRESHOLD`, `CLEANUP_INTERVAL_SECONDS`, `DISTRIBUTED_TASKS_ENABLED`, `CELERY_BROKER_URL`, `AUTO_PAUSE_ON_SILENCE`, `INTERRUPTION_THRESHOLD_AGGRESSIVE/BALANCED/STRICT`, `SESSION_LRU_MAX_SIZE`, `GOOGLE_CALENDAR_ID` are all declared and never consumed. Only `EXTERNAL_TIMEOUT_SECONDS` and `AGENT_TIMEOUT_SECONDS` (2 of the 19) are actually used. `config.py` is significantly aspirational — a lot of tuning knobs exist for subsystems (queueing, cleanup jobs, Celery) that were never built or were removed.

Key presence (names only, per L5):

| Key | Present? |
|---|---|
| GROQ_API_KEY, DEEPGRAM_API_KEY, MONGO_URI, PINECONE_API_KEY, NOTION_API_KEY, NEO4J_URI, NEO4J_PASSWORD, ANTHROPIC_API_KEY, OPENWEATHER_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, SERPER_API, ASTA_API_BEARER_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID | present |
| POSTGRES_URL, GOOGLE_SA_KEY_PATH | ABSENT |

The `/health/memory` and `/api/health` endpoints (two genuinely different implementations — see below) both report memory-layer health with a **hardcoded `True`** for L2/L3/L4 regardless of real connectivity (`memory/memory_engine.py:427-429`: `"l2_neo4j": True,  # If connect worked, assume healthy`). This is misleading monitoring, confirmed live: both my local cold-boot instance and the deployed AWS instance report `l2_neo4j:true` while Neo4j is provably unreachable on both.

**Duplicate/confusing health routes**, confirmed by reading both files: `backend/app/api/health.py:14,17` (`APIRouter(prefix="/health")`, mounted at `/api` → serves `/api/health/` with trailing slash, ISO timestamp, `{"status","service","timestamp"}`) is a genuinely different endpoint from `backend/app/api/routes.py:44-65` (`@router.get("/health")`, mounted at `/api` → serves `/api/health` **without** trailing slash, epoch timestamp, circuit-breaker + tool detail). Both are live, both return `200`, both say different things. `scripts/verify.sh` and `scripts/prove_memory_loop.py` poll the trailing-slash one; my `curl` of the deployed AWS box (no trailing slash) hit the other one — this is how I discovered the AWS box's `local_only` degraded-memory status (§G2).

---

## PHASE C — THE MEMORY LAYER, TRACED END TO END

### C1. WRITE PATH — and the two-system split

**System 1 — voice WS path** (`backend/app/services/memory/*`, built in commits `d12f6551`/`edf79ca9`, i.e. days ago):
1. `ws_transport.py:77-79` creates a session doc in Mongo `sessions` (`{session_id, turns:[], started_at, status}`) when a client connects.
2. `pipeline.py:91-92,124-125,137-138,144-145` appends each turn via `voice/session_store.py:append_turn()`.
3. `ws_transport.py:108-115` (inside the WS handler's `finally` block): on disconnect, calls `enqueue_extraction(session_id)` (`services/memory/outbox.py:10-47`), which inserts a Mongo `outbox` doc `{kind:"extract", status:"pending", payload:{session_id}}` — guarded against duplicate pending entries and against private sessions.
4. `core/outbox_worker.py:11-56` — a background `asyncio.Task` started at boot, polls `outbox` every 5s for `status:"pending"`, atomically claims one via `find_one_and_update`, calls `process_session_extraction()`.
5. `services/memory/extractor.py:54-156` — loads `prompts/session_extraction.md`, calls the LLM (`llm_factory.get_model("extraction")`) with the full transcript, validates against `ExtractionSchema` (insights, priority_signals, contradictions, emotional_state, open_loops). **Only the `insights` list is actually persisted** (`extractor.py:136-144`, `memory_handler.store_insight()`) — priority_signals, contradictions, emotional_state, and open_loops are extracted by the LLM and then silently dropped; nothing stores them. This matches the schema/storage mismatch the audit was told to look for.
6. If `graph_ltm.is_initialized`, the combined insight text is also passed to Graphiti (`graph_ltm.add_episode`) — a *third*, Graphiti-flavored Neo4j client, separate from the `memory/l2_graph.py` client used by System 2 below.

**System 2 — text-chat / `/api/chat` path** (`memory/memory_engine.py`, the older "5-layer" system: L1 Redis, L2 Neo4j via `memory/l2_graph.py`, L3 Pinecone via `memory/l3_vectors.py`, L4 MongoDB via `memory/l4_store.py`): reached via `routes.py:130-181` (`/api/chat`) → `supervisor_graph.run_supervisor_graph()` → `memory_engine.save_session()` (`memory/memory_engine.py:227-300`) on the way out, and `SessionManager.add_message()` separately. This is the system `main.py:378` connects at boot (`memory_status = await memory_engine.connect_all()`) and the one `/health/memory` and `orchestrator.cross_tier_retrieve()` (used by the OpenAI-adapter `/v1/chat/completions` endpoint) both talk to.

**These two systems do not share data.** A fact told to ASTA over voice never reaches `memory_engine`'s L2/L3/L4; a fact told via `/api/chat` never reaches the `insights` collection or Graphiti. **Confirmed by direct evidence**, not inference: I queried the shared `sessions` collection (which both systems write into, same DB `asta_db`, same collection name) and found three incompatible document shapes coexisting:

```
total sessions docs: 230
docs with turns[] (voice pipeline schema, System 1):        14
docs with messages[] (SessionManager's own schema, System 2 variant): 86
docs with workflow_type (memory_engine L4 SessionMetadata, System 2): 159
```

This schema collision is not theoretical — it produces a **real boot-time error**, captured live in the cold-boot log:
```
2026-07-19 23:25:19,864 - backend.app.services.session_manager - ERROR - Failed to restore active sessions: Document requires 'messages' field
```
`SessionManager.restore_active_sessions()` (called at every boot, `main.py:333`) queries `sessions` expecting its own `messages`-shaped documents and chokes the instant it hits a `turns`-shaped or `workflow_type`-shaped one from the other systems. It's caught and logged as a WARNING, not fatal, but active-session restoration is effectively broken on every single restart.

**Automatic trigger:** for System 1, extraction is genuinely automatic — no test, no manual step, it fires from `ws_transport.py`'s connection-close handler with no human in the loop, *when that handler runs* (see §C4 for why it currently doesn't). For System 2, `memory_engine.save_session()` is called from inside `supervisor_graph`'s graph execution on the `/api/chat` path — also automatic, not live-probed this session.

### C2. READ PATH

**System 1** (voice): `voice/memory_injector.py:22-65` — `MemoryContextInjector`, a Pipecat `FrameProcessor` sitting after STT and before the LLM. On every `TranscriptionFrame` (direction DOWNSTREAM), calls `services/memory/recall.py:recall(query, k=6)`, which:
1. Embeds the query (`memory.embeddings.embed`, sentence-transformers `all-MiniLM-L6-v2`, 384-dim, cached at module load — confirmed at `main.py:40`).
2. Fetches a similarity pool from Mongo via `db/memory_handler.py:get_relevant_insights()` — **not Atlas `$vectorSearch`; an in-memory cosine similarity over up to 1000 fetched docs** (`memory_handler.py:71-109`, explicit comment at line 69: *"For Phase 3, we fetch all insights and score them in-memory if Atlas Vector Search is not configured"*), threshold 0.3.
3. Fetches a relation pool from `graph_ltm.search()` (Graphiti).
4. Merges + dedupes by text, scores each as `0.5*behavioral + 0.3*recency(30-day half-life) + 0.2*similarity` (`recall.py:81`), returns top-k.
5. `memory_injector.py:51-55` builds a context block and pushes a `SystemPromptUpdateFrame`, which `pipeline.py`'s `RouterLLMService` (lines 59-66) splices into `messages[0]` (the system prompt) before the LLM call.

Given `insights` has zero documents (§C4), this entire read path has never had anything real to retrieve in production use — it is genuinely wired end-to-end in code, but empirically untested by real use because nothing has ever been written to read back.

**System 2** (text-chat): `memory_orchestrator.py:70-84` (`cross_tier_retrieve`) delegates entirely to `memory_engine.get_context_for_session()` (`memory/memory_engine.py:85-211`) — a genuinely more sophisticated pipeline (entity spotting → L1 cache check → L2 Neo4j cluster search → L3 Pinecone vector search → L4 Mongo fetch, with per-layer try/except fallback at each step) — not audited live this pass beyond confirming it's reachable and that its L2 (Neo4j) dependency is currently down.

### C3. Private mode

Enforced **only in System 1**: `pipeline.py:73-87` intercepts the literal strings `"private mode on"`/`"private mode off"` before they reach the LLM, calling `session_store.py:set_private()`/`clear_private()`. `outbox.py:24-27` and `extractor.py:73-75` both check the flag and skip enqueueing/extracting for `no_extract`/`no_trace` sessions. This is functional enforcement (skips a real write), not just a UI toggle — but I could not exercise it live this session in a way that proves recall-suppression, because System 1 has zero insights ever written regardless of private mode (§C4). No equivalent private-mode mechanism exists for System 2 / `/api/chat` — anything said there is unconditionally eligible for `memory_engine.save_session()`.

### C4. LIVE PROBE — the decisive one

I ran the actual live end-to-end acceptance script the previous work session wrote but, by its own admission in `docs/CLOSE_THE_LOOP_REPORT.md`, never got to execute ("Live run was **not completed** in this session due to local pipecat import failure preventing uvicorn boot"). This is the first time this probe has ever actually been run.

**Setup:** cold-booted the backend on a clean port (8792), confirmed `/api/health/` → 200. Found exactly one real registered device in Mongo (`registered_devices`, Karthik's `motorola edge 50 pro`, `device_id: 8b7f3a44d045` — reused this rather than registering a new device, to avoid touching the single-device policy). Ran:
```
PYTHONIOENCODING=utf-8 python scripts/prove_memory_loop.py --host http://127.0.0.1:8792 --device-id 8b7f3a44d045 --no-restart
```
(Note: the script crashes on stock Windows console encoding — `UnicodeEncodeError` on a `→` character in its own log helper, `scripts/prove_memory_loop.py:65` via `log()` at line 40 — a minor but real ❌ BROKEN-on-Windows finding, worked around with `PYTHONIOENCODING=utf-8`.)

**What happened, verbatim (trimmed):**
```
[prove] health OK: {"status":"ok","service":"ASTA Backend",...}
[prove] === SESSION A: state fact ===
[prove] WS connect → ws://127.0.0.1:8792/ws/conversation
[prove]   sent: 'My favorite chess opening is the Sicilian Najdorf (becb90).'
[prove]   recv: {"type":"text","text":"The Sicilian Najdorf, that's a sharp one, boss, ..."}
[prove] Session A session_id: 6b891858-ee47-42b4-b36d-7537b7a99adb
[prove] === Wait for outbox extraction ===
[prove]   polling outbox... pending=0 processing=1     (×60, over 120 seconds)
[prove] FAIL: Outbox never reached 'done' within timeout
```
The reply itself proves the voice round-trip and LLM routing work (§D5). The extraction wait timed out. I then inspected Mongo directly:
```
outbox docs matching my session_id 6b891858-...: ZERO
the one doc stuck in "processing": session_id "outbox-drain-67f08c7a", ts 2026-07-17 10:24:34
  → an orphaned leftover from tests/test_outbox_wiring.py's test_worker_drains_pending_task,
    run days ago and never cleaned up — the outbox worker has no stale-task recovery.
```
So the "processing=1" the probe saw the whole time was **stale garbage from a two-day-old pytest run, not my session** — the outbox worker has no mechanism to reclaim tasks orphaned by a crashed/killed process, which is itself a finding. But the more important discovery: **my session's own outbox document was never created at all.**

I checked the session document directly — it has both turns recorded correctly (real Mongo writes, `turns: [{role:user,...},{role:assistant,...}]`, no `private` flag set), which means `enqueue_extraction()` should have fired from `ws_transport.py`'s `finally` block on disconnect. It never did. Direct log evidence:
```
23:27:25,927 - WS_Conversation - INFO - [WS] Session 6b891858-... started
23:27:25,927 - WS_Conversation - INFO - [WS] Client connected (authenticated)
   ... (turn exchange happens, reply sent) ...
23:27:27,074 - INFO:     connection closed          ← transport-level close, confirmed
```
**`"[WS] Client disconnected (session ...)"` — the log line at `ws_transport.py:109`, which immediately precedes the `enqueue_extraction()` call — never printed, even 4+ minutes later, even though the underlying WebSocket transport logged `connection closed`.** This means `PipelineRunner.run(task)` (`ws_transport.py:104`) is not returning after the client disconnects — the pipeline task hangs, the `finally` block is never reached, and the automatic-extraction trigger never fires. This is not a probe artifact; it's a real, reproducible defect in the disconnect-handling path of the live voice pipeline.

**Final confirming number:** `db.insights.count_documents({})` → **0**, against **230** total session documents in this database's history. Zero insights have ever been extracted, from any session, ever, in this system's lifetime.

**Verdict: ASTA does NOT currently remember on its own.** The code for automatic memory formation is real and non-trivial, but the trigger that's supposed to fire it — session-close on the live voice pipeline — never runs, because the pipeline task itself never terminates when the client disconnects.

### C5. Memory inventory

```
insights:  0
sessions:  230
outbox:    2   (one orphaned "processing" doc from a stale test run, one from this audit's own probe)
reminders: 0
```
No sample insight docs to show — there are none. Of the 230 `sessions` docs, the schema split is documented in §C1 (14 / 86 / 159, roughly summing over 230 because shapes aren't perfectly mutually exclusive).

---

## PHASE D — LIVE SYSTEM PROBES

### D1. `make verify`

No `make` binary in this environment; ran the underlying `scripts/verify.sh` directly (equivalent). **Result: FAIL.**
```
--- (a) Import check: backend.app.main ---        [OK]
--- (b) Boot check: uvicorn + /api/health/ poll --- [OK] (200, no traceback)
--- (c) Pytest: docs/verification/probes backend/tests tests ---
6 failed, 47 passed, 7 warnings in 43.21s
[FAIL] pytest reported failing tests
```
This directly contradicts recent commit messages (`ccd6ca71 "close1: make verify is real now"`, `c93e45e4 "ship(gates): resolved known rot ... to ensure all verification gates are green"`) — per L2, those are claims; the actual current state is red. Failures broken down:

- `docs/verification/probes/test_persona_injection.py::test_persona_injection_real_wire` — a genuine, trivial mismatch: the test asserts the string `"You are ASTA, Karthik's personal assistant"` is present; the actual persona text is `"You are ASTA, Karthik's personal **AI** assistant."` (`backend/app/core/persona.py`) — one word off, a stale test string, not a real bug in the persona code.
- `tests/test_outbox_wiring.py` — 5 failures, all `TypeError: object MagicMock can't be used in 'await' expression` at `session_store.py:17` (`db_manager.db["sessions"].insert_one(...)`). Root cause identified by reading the test file: `_ensure_mongo()`'s pollution guard (`tests/test_outbox_wiring.py:31-37`) does `if not hasattr(db_manager.db, "sessions"): await db_manager.connect()` — but `hasattr()` on a `unittest.mock.MagicMock` is **always true** for any attribute name (Mock auto-creates them), so the guard can never detect that an earlier test in the same pytest run replaced `db_manager.db` with a mock and never restored it. This is a test-isolation bug in the test suite, not evidence the outbox code itself is broken — the boot check in the same run independently proved the server boots clean.

### D2. Cold boot — full log, redacted

Started `uvicorn backend.app.main:app` on a clean port, polled `/api/health/` to 200, captured every WARNING/ERROR/CRITICAL line (deduplicated, retry-spam collapsed):
```
[ENV] OPTIONAL MISSING: GOOGLE_SA_KEY_PATH → Calendar tool disabled
[ENV] Starting in DEGRADED mode. Missing: 1 optional vars
Degraded Mode Status: Spacy model missing or failed ([E050] Can't find model 'en_core_web_sm'...)
Degraded Mode Status: Database Health Check Failed! Some systems may run offline.
DatabaseManager - ERROR - Neo4j Authentication Error or Instance Unavailable: Failed to DNS resolve address 34e6ab76.databases.neo4j.io:7687
Failed to restore active sessions: Document requires 'messages' field     ← the schema-collision error, §C1
Wake Word Detection failed to initialize: Could not find pretrained model for model name 'hey_asta'
memory.l2_graph - ERROR - Failed to connect to Neo4j: [same DNS failure]
Checkpointer - WARNING - MongoDB checkpointer unavailable (No module named 'langgraph.checkpoint.mongodb.aio'); falling back to in-memory MemorySaver
graphiti_core.driver.neo4j_driver - ERROR - Error executing Neo4j query: [same DNS failure]  (repeated ~20×, background Graphiti index-build retries)
```
Then: `Application startup complete. Uvicorn running on http://127.0.0.1:8792`. `/api/health/` → `{"status":"ok",...}`. `/health/memory` → `{"l1_redis":true,"l2_neo4j":true,"l3_pinecone":true,"l4_mongodb":true,...}` — **the `l2_neo4j:true` is false-positive** per §B5.

Every degraded item above is caught and logged, not fatal — the server boots and serves despite Neo4j, spaCy, and wake-word-model being unavailable. That's a real strength of the try/except-everywhere startup design; the flip side is these WARNINGs are easy to miss and the health endpoints actively hide the Neo4j failure.

### D3. `scripts/` inventory

- `verify.sh` — run, see D1.
- `prove_memory_loop.py` — run, see C4.
- `backup.sh` / `backup_restore.py` — read but **deliberately not executed**. `backup.sh` writes a canary record to the live Mongo + Neo4j, dumps both, tars the archive, restores into scratch targets, verifies the canary round-tripped, then deletes the canary from the live stores. This is a legitimate, well-designed non-destructive backup+restore-proof script (matches the "close4: backup + tested restore" commit) — but Neo4j is currently unreachable, so a live run right now would only prove the Mongo half and fail/hang on the Neo4j half. Given the audit's read-only mandate and that Neo4j is already known-down, running it wouldn't add new evidence proportional to the risk of touching live data via a script I hadn't dry-run first; I opted not to execute it. Tag: UNKNOWN — because not run, by deliberate choice, not because it's broken.

### D4. Reminder probe

Could not exercise this through the live FastAPI process without adding new server code (out of scope — read-only), so I ran the identical `reminder_service`/`scheduler_service` singletons directly in a standalone script against the real Mongo — same code path, same APScheduler mechanics, just not inside the uvicorn process. Scheduled a reminder 15 seconds out:
```
[probe] scheduled reminder_id=6a5d1156bcb06f8fe466eba7 due=2026-07-19T18:03:17Z
[probe] state -> scheduled at 18:03:02Z
[probe] state -> awaiting_ack at 18:03:19Z
[probe] PASS: reminder fired and transitioned past 'speaking'
```
✅ VERIFIED-LIVE — the reminder fired within 2 seconds of its due time and correctly walked the `scheduled → speaking → awaiting_ack` state machine (took the FCM-simulated branch since no WS client was connected, exactly as `reminder_service.py:111-118` says it should). Probe doc cleaned up afterward.

### D5. LLM router probe

Captured as a side effect of the §C4 probe — a real completion, not a mock:
```
httpx - INFO - HTTP Request: POST https://api.groq.com/openai/v1/chat/completions "HTTP/1.1 200 OK"
reply: "The Sicilian Najdorf, that's a sharp one, boss, lots of counterplay for Black, can get really tactical."
```
✅ VERIFIED-LIVE — Groq answered, in persona ("boss"), via `llm_factory.router` → `pipeline.py`'s `RouterLLMService`. Quota ledger state not separately inspected this pass (Redis-backed, `llm_factory.py:22-46`).

---

## PHASE E — FRONTEND & FACE

*(Full findings gathered by a dedicated read-only sub-agent this session; file:line citations verified against the live tree.)*

**Stack:** React 19.2.4 + Vite 8.0.1 + TypeScript/JSX mix. Entry `frontend/index.html`→`src/main.jsx`→`App.jsx`.

**The orb — seam confirmed real:** `orb/orbScene.ts` (885 lines), `handTracker.ts` (271 lines), `ultron.css` (235 lines) were added wholesale in one commit (`3adcd4a3`) — consistent with dropping in an external "Ultron UI" three.js template. `handTracker.ts` and `ultron.css` contain **zero** ASTA-specific markers. `orbScene.ts` carries a literal delimiter comment `// ═══ ASTA SEAM ═══` at line 702, bounding a small ~15-line block (`ASTA_STATES`/`ASTA_PARAMS`/`setAstaState()`) that only tweaks a few multipliers consumed by the otherwise-untouched render loop; commit `067ab5d7` shows this exact block being *moved*, not rewritten, confirming it's a thin patch on unmodified template code. `orb/AstaOrb.tsx` (renamed from `JarvisOrb.tsx` at 97% diff-similarity — cosmetic) has an analogous marked block, `{/* ASTA INTEGRATION */}`.

**HUD:** lives directly inside `AstaOrb.tsx` (no separate Hud component) — status line, mic/text-input controls, and a single-message subtitle bubble showing only the *last* assistant reply.

**Browser wake word** (`App.jsx:973-1033`, added `d81d8294`): `window.SpeechRecognition || window.webkitSpeechRecognition` (Chrome-only in practice), `continuous:true`, substring-matches `"asta"|"aster"|"hey asta"|"hay asta"|"hasty"` against both interim and final transcripts. Auto-restarts on `onend` while idle. No dedicated wake-word model — a generic always-on STT substring match, not comparable to the on-device openWakeWord approach used server-side/on mobile. Notably, this same commit **removed** `&trigger=wake_word` from the WS connection URL, so the backend's own `ServerWakeWordConfirmProcessor` (§B3) is no longer engaged by the web client at all.

**❌ Critical finding — frontend/backend WS protocol mismatch, static evidence, not live-tested:** the live backend (`ws_transport.py`) sends `{"type":"orb_state","state":...}` and `{"type":"text","text":...}` messages, and audio with no framing header. `App.jsx`'s `handleMessage` has **no case for `orb_state` or `text`** at all — it's coded against a `status`/`llm_chunk`/`transcript`/`audio_end` protocol with a 4-byte sequence-ID audio header, which matches `turn_processor.py` exactly — and `turn_processor.py` is confirmed dead code (§B4, never registered as a route, its `TurnProcessor` class never instantiated). Net effect: against the actual live backend, the shipped frontend would silently ignore every orb-state and text-reply message (no HUD update, no subtitle), and misparse every real audio chunk by treating its first 2 audio samples as a bogus sequence header. This is a real, evidenced (not merely inferred) integration break between two pieces of code that were each touched in the last few days without reconciling their wire contract.

**Config:** `frontend/config.js` is tracked in git (not gitignored) with a real, non-placeholder bearer-token literal — the same value also hardcoded as a fallback in `App.jsx:7`, i.e. a real secret duplicated across two committed source files (value redacted here per L5; flagged as a rotation candidate, especially since a prior commit `ea26341e` is literally titled "rotate leaked token", suggesting this has already happened once before). `DEVICE_ID` in the same file is still the literal placeholder `"your_device_id_here"` — half-configured. Backend `ASTA_API_BEARER_TOKEN` confirmed present (§B5); direct value comparison between the two was not attempted (never printing secret values, per L5).

**Headless start:** ✅ VERIFIED-LIVE — `npm run dev` served on a clean port, root HTML and `main.jsx` both returned 200. Backend not required for basic page render (WS connect is deferred/non-blocking).

---

## PHASE F — MOBILE APP DEEP AUDIT

*(Gathered by a dedicated read-only sub-agent auditing the private `ASTA_APP` submodule. Full identical content also committed as `docs/STATE_OF_MOBILE_2026-07-19.md` inside that repo per the mission's R2, so the private repo self-documents.)*

**Stack:** Mixed Kotlin (24 files) + Java (17 files) — a Kotlin migration in progress, with the newer subsystems (network, service, audio, alarm) in Kotlin and older ones (main UI, the legacy voice stack) still in Java. `compileSdk`/`targetSdk` 36, `minSdk` 26, JVM target 17, AGP 8.13.2, Gradle 8.13.

**Wake word — 🟡 WIRED-UNPROVEN, and mislabeled.** On-device openWakeWord via ONNX Runtime (offline, no cloud dependency) — architecturally solid. But the actual shipped model is openWakeWord's **stock `hey_jarvis.onnx`** (`service/OpenWakeWordEngine.kt:54`), while every piece of UI and notification text claims the phrase is **"Hey ASTA"** (`WakeWordService.kt:51`, `strings.xml:4`, `MainActivity.java:617`). No custom "Hey ASTA" model exists anywhere in the repo. **The app will only ever actually respond to "Hey Jarvis," not the phrase it tells the user to say** — directly mirroring this audit's main-repo finding that the server-side `hey_asta` model also fails to load (§D2, §H1) because it was likewise never trained.

**Backend URL resolution (traced end-to-end):** `BuildConfig.SERVER_URL` default (`http://[AWS-host-redacted]:8000/`, confirmed live in §G2) → persisted `SharedPreferences` override via `ConfigManager` → a first-launch dialog that can auto-probe a local ngrok inspector or accept manual entry. `network/NgrokUrlFetcher.kt` is fully dead code (zero call sites) — `MainActivity` reimplements the same ngrok-probing logic inline instead, redundantly.

**Foreground services, but not boot-durable.** Three real foreground services exist (`WakeWordService`, `ASTAForegroundService`, `ProactiveListenerService`), each with a coherent implementation. But `alarm/BootReceiver.kt`, despite being correctly registered for `BOOT_COMPLETED`, **only reschedules the morning alarm** — it does not restart any of the three listener services. After any device reboot, wake-word detection and proactive reminder delivery are both dead until the user manually reopens the app. Compounding this: **no battery-optimization/Doze exemption is ever requested anywhere in the codebase** (zero matches for `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` or equivalent) — standard Android background restrictions can suspend these "always-on" services with no code-level mitigation. Net effect: this is structurally **not** yet a 24/7 background listener, regardless of what runs while the app happens to be freshly opened.

**The manual voice path is explicitly disabled.** `MainActivity.java:366-368`: the record button's handler is just `showToast("Voice mode disabled. Text only communication is active.")` — the entire legacy Java `assistant/` voice stack (`AssistantController`, `SpeechManager`, `TTSManager`) and its `VoiceAssistantActivity` screen are dead, unreachable code (commented-out wiring, zero launch call sites). The *only* live voice entry points in the shipped app are wake-word detection and the morning-alarm flow — there is no user-initiated tap-to-talk fallback if wake word fails or is unavailable.

**❌ CRITICAL — a real production bearer token is permanently recoverable from git history.** Commit `d43594d` ("fix(secrets): move bearer token to local.properties BuildConfig") is a real, correctly-implemented fix at the code level — verified: `local.properties` is properly gitignored and was never tracked, `local.properties.example` contains only a placeholder, and no bearer-token string literal remains in any tracked source file at HEAD. **But it only removed the secret from the current tree, not from history.** The literal token value (redacted here per L5; a fixed default-token string used in three source files) is still present in plaintext in three already-pushed ancestor commits (`a2e9d44`, `bbda79a`, `bd55827`) reachable via `origin/master` on GitHub right now. Per L5 this is reported as a finding, not fixed or printed further — but it should be treated as a compromised credential requiring rotation on the backend regardless of the recent cleanup commit, and the repo's history should be considered exposed for as long as it remains unscrubbed.

**Build truth — ❌ BROKEN, right now, in this environment.** Toolchain is fully present (JDK 21, Android SDK with platforms 31–36, Gradle wrapper 8.13) — not a missing-toolchain problem. `./gradlew.bat assembleDebug` fails at **Gradle configuration time**, before any app source is even compiled:
```
e: file:///.../app/build.gradle.kts:7:28: Unresolved reference: util
Line 7: val localProperties = java.util.Properties()
```
This is on the exact line the secrets-fix commit (`d43594d`) itself introduced, in `app/build.gradle.kts:7`. Reproduced twice (`assembleDebug` and `help --stacktrace`), and since it fails at root-script compilation it blocks **every** Gradle task — the app's actual Kotlin/Java code was never reached to be validated. Root cause not further diagnosed (read-only audit), but the practical fact is: **this repo does not currently produce an APK.**

**Offline behavior:** genuinely solid for typed chat only — SQLCipher-encrypted local queue + WorkManager sync-on-reconnect (`SyncWorker.kt`, `AstaDatabaseHelper.kt`). No equivalent exists for voice/wake-word sessions — a dropped connection during a voice session just retries a few times, then gives up silently with no local caching.

**Other secrets-scan items (report-only, INFO/LOW severity, not fixed):** a hardcoded dead-code ngrok WSS URL in the unreachable `AssistantController.java:46`; `android:usesCleartextTraffic="true"` in the manifest, consistent with the plain-`http://` backend URL — meaning the bearer token and privacy-sensitive Health Connect data (`DailyMetricsWorker` posts steps/sleep to `/api/metrics/daily`) currently travel unencrypted over the network; a tracked Firebase `google-services.json` with a client API key (Google-documented as non-secret when package-restricted, flagged for verification only).

**Verdict:** a structurally coherent skeleton for the target architecture — real on-device wake-word inference, a real WS voice pipeline talking to the confirmed-live backend, a genuinely working offline-sync path for text, and a Doze-resistant alarm scheduler — but currently **un-buildable, not boot-durable, not Doze-resistant for its "always listening" services, missing any voice fallback UI, mislabeling its own wake phrase, and carrying a compromised credential in already-pushed git history.** It is meaningfully further from "24/7 ASTA in the pocket" than the presence of all these subsystems might suggest at a glance.

---

## PHASE G — INFRA, DEPLOYMENT & SECURITY POSTURE

### G1. `.env` census
See §B5 table — 15 of 17 checked keys present, `POSTGRES_URL` and `GOOGLE_SA_KEY_PATH` absent (both are optional-feature keys per `config.py`/`env_validation.py`: Postgres checkpointer falls back to in-memory, Calendar tool disables).

### G2. Server truth — something IS live

`ops/DEPLOY.md` describes an Oracle Cloud + `docker compose` runbook with a placeholder `<instance-ip>` — no real host committed there. `render.yaml` targets Render but the prior audit's own probe (`docs/CLOSE_THE_LOOP_REPORT.md`) found the Render URL 404s ("Not Found") — not currently deployed. The mobile app's `app/build.gradle.kts` hardcodes a real, working AWS-style IP as its default backend. I curled it directly:
```
$ curl -m 8 http://<AWS-host-redacted>:8000/api/health/
HTTP 200 — {"status":"ok","service":"ASTA Backend","timestamp":"2026-07-19T18:04:04Z"}

$ curl -m 8 http://<AWS-host-redacted>:8000/api/health
HTTP 200 — {"status":"ok","database":"connected","memory_mode":"local_only",
  "services":{"mode":"local_only","l1_status":"operational","l2_status":"operational",
  "l3_status":"degraded","redis_status":false,"mongodb_status":false,
  "neo4j_status":false,"pinecone_status":false}, ...}
```
**Verdict: something IS live** at that AWS host, answering real requests. But its detailed status summary (the `/api/health` variant, §B5) shows `redis_status`/`mongodb_status`/`neo4j_status`/`pinecone_status` all `false` — it's running in `local_only` degraded mode, on what is almost certainly older code than this branch (the timestamp format alone differs from the `/api/health/` variant, and `docs/CLOSE_THE_LOOP_REPORT.md`, written two days ago, already flagged this exact host as running "pre-M1 code (no outbox wiring)"). Nothing has been redeployed since. This independently corroborates the Neo4j-down finding (§D2) — the *same* Aura cluster is unreachable from a completely different network/host, which rules out "it's just my local DNS" and points to the Aura instance itself being paused or deleted.

Per L2, I did not take the mobile app's or `ops/DEPLOY.md`'s narrative at face value — the curl above is the actual evidence.

### G3. Databases
Mongo Atlas: ✅ reachable (this session connected repeatedly, read/wrote real documents). Neo4j Aura: ❌ unreachable — DNS resolution fails for the configured host from two independent machines (this one and the deployed AWS box). Pinecone: ✅ reachable (index stats logged at boot: `L3 Pinecone connected, index: asta-memory-v2`). Redis: ✅ reachable locally. Free-tier usage levels: UNKNOWN — because no dashboard/API-quota check was performed this pass (out of scope of what boot logs surface).

### G4. Secrets history
`.env` and `frontend/config.js` are both **currently untracked or tracked-with-real-secrets respectively** — `.env` is not in `git ls-files` (untracked, correct); `frontend/config.js` **is** tracked with a real token (§E) — a live, uncorrected exposure, not just history. Prior rotation did happen at least once (`ea26341e "wirefix3: rotate leaked token"`, and mobile-side `d43594d "fix(secrets): move bearer token to local.properties"`), but the frontend `config.js` token was not part of either rotation and remains committed today.

### G5. CI
`.github/workflows/ci.yml`: triggers only on push/PR to **`master`**. Every commit examined in this audit (§A3) is on `face-and-soul`, which has never triggered this workflow — confirmed by the trigger config alone (`ci.yml:4-7`), not by checking run history (GitHub Actions run history wasn't queried this pass — UNKNOWN whether it's even connected/enabled on this repo, because that requires `gh` API access not exercised here). The CI test surface itself is also narrower than local `verify.sh`: `pytest tests/` only, skipping `docs/verification/probes` and `backend/tests` entirely — so even if it were triggering, it wouldn't catch the `test_persona_injection` failure found in §D1 (that lives under `docs/verification/probes/`).

---

## PHASE H — DELTA LEDGERS

### H1. Delta vs. blueprint (`docs/ASTA_BLUEPRINT_V2.md`)

| Designed (v2 blueprint) | Built (this audit's findings) | Divergence |
|---|---|---|
| "Storage consolidation: Mongo = source of truth + vectors; Neo4j+Graphiti = graph; **Pinecone deleted**" (D11) | Pinecone is very much still alive and connected at boot (`main.py:282-326`); it's `memory_engine`'s L3, still wired into System 2's read/write path | Consolidation never happened — the blueprint's target architecture assumed one memory system, but the codebase still runs the pre-blueprint `memory_engine` (System 2) *alongside* the new outbox-based System 1 the blueprint actually describes |
| "Ingestion → auto-extraction on session end (one Groq call)... fully automatic after one-time architecture walkthrough" (D13, D20) | Extraction code matches this design closely (§C1) — but the trigger that's supposed to fire it on session end never runs (§C4) | Code matches the design; the live behavior does not, because of the disconnect-handling bug |
| "Private mode: 'ASTA, off the record' → session flagged; no extraction/vectors/graph writes" (D18) | Implemented via literal string match (`"private mode on"`), not a natural "off the record" phrase; enforcement logic matches the design | Mechanism simplified from natural-language intent to exact string match |
| "Custom 'Hey ASTA' wake model via livekit-wakeword... ~100x fewer false positives than openWakeWord" (v1 table, row 8; D30) | Still running stock openWakeWord, and the configured model name `hey_asta` **fails to load** at boot (`Could not find pretrained model for model name 'hey_asta'` — confirmed live, §D2) — no custom model was ever trained (blueprint's own OPEN-2 item, "record ~50 clips," was never done) | Wake word detection is currently non-functional server-side; the browser's generic Web Speech substring-match (§E) has become the de facto wake mechanism instead |
| "Migrate the realtime loop to Pipecat... barge-in, Silero VAD" (D23) | Done — `pipeline.py` is built on Pipecat with Silero VAD | Matches design |
| R1: "backend must boot before anything else matters... current state: it doesn't" | Backend now boots cleanly (§D2) | This specific blueprint complaint has been resolved since v2 was written |
| R2: "CI or it will happen again... two Sev-1 bugs are literally a syntax error and a missing import" | `research_service.py` has exactly this class of bug right now — a missing-module import (§H2) — and CI (§G5) targets the wrong branch, so it would not have caught it even if it were the same class of failure the blueprint was worried about | The exact failure mode R2 was written to prevent has recurred, on a branch CI doesn't even watch |
| R3: attic list explicitly named `instagram_graph.py, linkedin_graph.py, youtube_graph.py, youtube_engine.py, content_engine.py, content_manager.py...` for deletion | `instagram_graph.py`, `linkedin_graph.py`, `youtube_graph.py` are confirmed dead (§B4) and still present, undeleted; `youtube_engine.py`, `content_engine.py`, `content_manager.py` are **not** dead — they're live via `action_executor.py`/`supervisor_graph.py` (§B4) — the blueprint's own attic list was wrong about these three | Partial execution of R3; the blueprint's dead-code diagnosis itself was partially inaccurate |
| Target: Oracle Cloud Always-Free ARM hosting | Actually deployed: an AWS host (§G2), running stale code | Different cloud than planned, and not kept current |
| "`/health` reports per-dependency truth" (R5) | Reports **false-positive** truth for L2/L3/L4 (hardcoded `True`, §B5) | Directly contradicts this design principle |

### H2. Recent-changes ledger (last 2 weeks, both repos, themed, verified via diffs not messages)

- **Memory system (main repo, `d12f6551`→`edf79ca9`→`c601e500`, all 2026-07-17):** genuinely new outbox/extractor/recall/graph_ltm stack added — real code, confirmed live-broken at the disconnect-handling step (§C4). Also in this window: `research_service.py` broke — confirmed by direct traceback:
  ```
  $ python -c "import backend.app.services.research_service"
  ModuleNotFoundError: No module named 'backend.app.services.memory_service'
  ```
  `research_service.py:11` imports a `memory_service` module that does not exist anywhere in the tree. Any code path reaching it crashes: the voice pipeline's "look into X / research X / deep dive on X" intent (`pipeline.py:111-120`, **not** wrapped in a try/except — this would propagate as an unhandled exception in that frame processor), and the `weekly_radar` scheduled job (§B2). UNKNOWN which commit introduced this specific breakage — `git log` history for `memory_service.py` wasn't traced this pass, but the module is absent from the current tree regardless of when it went missing.
- **Identity/branding (main repo, `d81d8294`, `e06149d0`):** Friday/Jarvis → ASTA rename across persona and UI, confirmed via diff (persona.py, App.jsx, JarvisOrb→AstaOrb rename). Real, mostly cosmetic + prompt text, plus the new browser wake-word feature bundled into the same commit.
- **UI (main repo, `3adcd4a3`→`067ab5d7`→`fe7ff223`):** the "Ultron UI" three.js orb template was dropped in wholesale, then a crash was fixed, then most of an intermediate customization pass was reverted back toward the stock template with ASTA controls re-injected as a marked seam (§E). Net effect over the window: a lot of churn landing back close to the original template state.
- **Wake word / config (main repo, `c601e500`):** deleted two route files outright, retargeted wake-word model name to `hey_asta` — which then fails to load at boot (§H1) since no such model was ever trained.
- **Mobile (`ASTA_APP`, `bd55827`→`bb7910d`→`298cf80`→`d43594d`):** wired to the AWS backend, purged hardcoded ngrok fallbacks in favor of `BuildConfig.SERVER_URL`, added a real wake-word/audio-streaming service, and finally moved the bearer token out of source into `local.properties` — a real, verifiable secrets-hygiene fix (confirmed structurally reachable via `BuildConfig`, per the mobile sub-agent's report).
- **Fixes/reports (main repo, `a56f3bcc`, `bae2d5d3`):** the previous work session's own closing report explicitly documents that its two most important claims — the live M2 memory-loop proof and a clean `make verify` run — were **not actually executed**, only prepared. This audit executed both for the first time and found both fail (§C4, §D1).

---

## TOP 10 FINDINGS (ranked by impact on 24/7 + remembers everything + laptop & mobile)

1. **❌ A real production bearer token is permanently recoverable from the mobile repo's git history** — 3 already-pushed ancestor commits on `origin/master` contain it in plaintext, despite a real, correctly-implemented code-level fix in the current HEAD. This is the single highest-severity item in the whole audit: it's a live, exploitable credential exposure, not a code-quality issue. (§F)
2. **❌ Automatic memory formation is completely non-functional in production use** — 230 sessions, 0 insights, ever. Root cause: the voice WS pipeline task doesn't return after client disconnect, so the enqueue-on-close trigger never fires. (§C4)
3. **❌ Two parallel, non-interoperating memory systems** write to the same database, sometimes the same collection, with 3 incompatible schemas, causing a real (if non-fatal) boot error. A fact told by voice is invisible to text chat and vice versa. (§C1, §H1)
4. **❌ Neo4j Aura (the graph layer for both memory systems) is unreachable** from two independent hosts — almost certainly the free-tier instance has been paused or deleted. Every health check hides this behind a hardcoded `True`. (§D2, §G3, §B5)
5. **❌ The mobile app does not currently build** (Gradle config-time script error, reproduced twice) and is not boot-durable — `BootReceiver` never restarts the wake-word/foreground listener services after a reboot, and no battery/Doze exemption is ever requested. "24/7 in the pocket" is not close on the current codebase, independent of the backend issues. (§F)
6. **❌ `research_service.py` cannot even be imported** (`ModuleNotFoundError: memory_service`) — breaks the voice "research X" intent and the weekly-radar scheduled job. (§H2)
7. **❌ Frontend/backend WebSocket protocol mismatch** — the shipped web UI has no handler for what the live backend actually sends, and would misparse real TTS audio due to a framing-header mismatch. Confirmed via static code trace across both sides. (§E)
8. **❌ `make verify` fails** (6/53 tests red), directly contradicting the last work session's "all gates green" commit messages — one stale test string, plus a test-isolation bug (`MagicMock` defeating its own pollution guard). (§D1)
9. **🟡 Wake word is mislabeled and non-functional on both platforms** — the server-side `hey_asta` openWakeWord model fails to load at boot (never trained), and the mobile app ships the stock `hey_jarvis.onnx` model while every piece of its UI text claims the phrase is "Hey ASTA." Neither platform will respond to the wake phrase it advertises to the user. The browser's generic Web Speech substring-match has become the de facto (Chrome-only) wake mechanism on web. (§D2, §E, §F, §H1)
10. **✅ What actually works, cleanly, end to end:** the scheduler (9 real jobs, self-monitoring included), reminder delivery (proven live: scheduled → fired → acked-state in ~17s), and LLM routing via Groq (real completion, in persona). These are the solid foundation the rest should be built on. (§B2, §D4, §D5)

---

## OPEN DECISIONS (only Karthik can make these)

1. **Which memory system survives?** System 1 (outbox/extractor/insights/Graphiti) matches the current blueprint's design intent but is broken at the trigger step; System 2 (`memory_engine` L1-L4) is older, more elaborate, still fully wired, and nothing here evidences it's broken — it just wasn't live-probed this session. Keeping both indefinitely guarantees continued schema collisions like the one found in §C1.
2. **Neo4j Aura: recreate the instance or drop the graph layer?** Both memory systems currently degrade "successfully" without it (frontend/pipeline still functions), but "remembers everything" as a goal specifically wants the graph/relationship layer the blueprint designed. Decide whether to pay the 10 minutes to spin up a fresh free Aura instance and update `NEO4J_URI`, or formally retire the graph tier from the architecture.
3. **Deploy target:** the live AWS box is running stale, degraded-memory code with no clear redeploy plan in this repo (`ops/DEPLOY.md`'s Oracle runbook has a placeholder IP, never filled in). Decide the actual hosting target before investing further in server-side features.
4. **Fix-or-retire the browser frontend's WS handler** — given §E's finding, is the web UI meant to be a real client going forward (in which case its message handling needs to be rewritten against the actual live protocol), or is voice-via-mobile/PC-client the real target and the web UI is a secondary surface that can wait?
5. **Rotate the `frontend/config.js` token now**, and separately rotate whatever token the mobile app's now-purged-from-HEAD-but-not-from-history default token literal (§F) maps to on the backend — two independent live/historical secret exposures, both actionable today regardless of any other decision above.
6. **Mobile: fix the build before doing anything else with it** — every other mobile finding (wake-word mislabeling, boot persistence, Doze exemption) is moot until `app/build.gradle.kts:7`'s config-time error is resolved and an APK can actually be produced again.
7. **Decide whether to scrub the mobile repo's git history** for the leaked token, given it's a private repo with one collaborator — lower urgency than immediate rotation, but worth a decision either way rather than leaving it unaddressed indefinitely.

---

## SECRETS CHECK

Ran the mandated grep before treating this report as final:
```
grep -inE "key.*=|token.*=|mongodb\+srv|neo4j\+s|Bearer [A-Za-z0-9]" docs/STATE_OF_EVERYTHING_2026-07-19.md
```
Result: no live key/token values present — mentions of "token"/"key" in this document are structural/descriptive only (e.g. "bearer token literal", "GROQ_API_KEY: present"), with all secret values redacted per L5.
