# ASTA — WHAT WE HAVE (Current State Report)
> Snapshot date: 2026-07-07. Verified live against EC2 backend (98.86.139.178:8000) and the physical Motorola Edge 50 Pro.
> Companion file: `ASTA_IMPLEMENTATION_PLAN.md` (what to build next).

---

## 1. AWS BACKEND — ✅ RUNNING (fixed this session)

**Server:** EC2 Ubuntu, FastAPI + uvicorn as systemd service `asta`, port 8000 open in security group.
**Endpoint:** `http://98.86.139.178:8000/` (HTTP/WS — no SSL yet). ngrok tunnel still running but no longer needed by the app.

### Fixed this session (was crash-looping 8,385 times — port 8000 never stayed open)
| Bug | File (on server) | Fix |
|---|---|---|
| `registry.initialize()` / `registry.shutdown()` called but never existed | `backend/app/main.py` lifespan | Removed; lifespan now calls the real handlers |
| `lifespan=` param silently disabled `@app.on_event` startup (DB/Redis/Pinecone/scheduler never ran) | `backend/app/main.py` | lifespan explicitly awaits `startup_event()` / `shutdown_event()` |
| `synthesize_proactive_audio_b64` imported but never defined anywhere | `backend/app/api/ws_transport.py` | Implemented (collects Deepgram TTS stream → base64) |
| `asyncio.create_task()` handed a Motor future (crashed every successful auth) | `backend/app/auth/token_auth.py` ×2 | Wrapped in real coroutines |

### Verified working now
- Health: `GET /api/health/` → 200 OK
- MongoDB Atlas ✔, Neo4j Aura ✔, Redis ✔, Pinecone ✔ (index `asta-memory-v2`, 99 vectors, dim 384)
- 63 active sessions restored from Mongo on boot
- Scheduler running: morning alarm 5:30 AM IST + night planning 10:30 PM IST + accountability monitor every 15 min
- 5 tools registered: search, weather, news, notion, image
- Device auth: single-device binding enforced; phone `8b7f3a44d045` registered
- Phone's WebSocket `/ws/conversation` connects **authenticated** direct to AWS
- FCM token registration (`POST /api/device-token`) → 200 OK

### ⚠️ Known degraded / unfixed on server
- **Server patches are uncommitted** — `git status` on EC2 shows modified `main.py`, `ws_transport.py`, `token_auth.py`, `settings_routes.py` not in git. A redeploy/pull would wipe the fixes.
- spaCy `en_core_web_sm` missing → entity extraction degraded (hurts memory writes)
- `summa` module missing → SagaRetryWorker (legacy memory pipeline) fails at startup
- `CacheService.set error: Object of type datetime is not JSON serializable` — ~60 errors on every boot during session restore (sessions restore but cache writes fail)
- L1.5 speculative prefetch kwargs mismatch (known bug from audit, still present at `memory_orchestrator.py:60`)
- `GOOGLE_SA_KEY_PATH` missing → Calendar tool disabled
- No HTTPS/domain — traffic is plaintext HTTP; token rides in query params on WS

---

## 2. MOBILE APP — ✅ BUILDS, INSTALLS, CONNECTS TO AWS (fixed this session)

**Stack:** Native Android Kotlin/Java + embedded Flutter module, SQLCipher offline DB, ONNX wake word.

### Fixed this session
- 30+ compile errors (missing imports, wrong packages: `net.zetetic` → `net.sqlcipher`, `ConfigManager` package, `AstaNetworkClient.api` → `.apiService`, `HealthConnectClient.sdkStatus` → `getSdkStatus`, WakeUpActivity phantom `R.id` references, deprecated OkHttp calls)
- `BASE_URL` / `ConfigManager` default now `http://98.86.139.178:8000/` (was dead ngrok URL); one-time migration overwrites cached ngrok URLs
- **Device self-registration on launch** (`POST /api/device/register`) — this call didn't exist before; no fresh install could ever authenticate
- FCM registration was missing the `X-Device-Id` header → 403; fixed → 200
- Wake-word pipeline rebuilt as the correct **3-stage** openWakeWord chain: `melspectrogram.onnx → embedding_model.onnx (was completely missing from assets — copied in) → hey_jarvis.onnx`. Runs error-free, computes confidence every 80 ms chunk.
- `MainActivity` now requests RECORD_AUDIO and starts `WakeWordService` (was never started by anything)

### Services confirmed running on the phone
- `ProactiveListenerService` — audio-free WS listener for reminder broadcasts → shows notifications
- `WakeWordService` — mic open, ONNX pipeline processing chunks live

### ⚠️ Wake word detection NOT yet firing — root cause found, fix half-applied
openWakeWord expects **raw int16 PCM cast to float32** (not normalized ÷32768 — that fix IS applied) **and** a `/10 + 2` transform on the mel output before the embedding model (**NOT yet applied** — was interrupted mid-edit in `OpenWakeWordEngine.kt::extractMelspectrogram`). Until that lands, confidence stays ~1e-6 and "Hey Jarvis" won't trigger. This is the first item in the plan.

---

## 3. VOICE PIPELINE — INFRASTRUCTURE EXISTS, END-TO-END UNVERIFIED

**What exists (code-complete):**
- `ASTAForegroundService`: mic → PCM chunks → WS → backend; energy-based VAD (1.5 s silence → `turn_end`); plays 24 kHz PCM TTS responses; handles `transcript / response / audio / stage / proactive_audio / asta_proactive` message types
- Backend: WS PCM → Deepgram nova-2 STT → LangGraph supervisor → Groq/Gemini LLM → Deepgram TTS → PCM back
- Silent-mode toggle (app switch + quick-settings tile → `POST /api/settings/silent`)

**What's NOT working / unverified:**
- Wake word detection (blocker above) → `ASTAForegroundService` never gets started
- **In-app voice is explicitly disabled**: mic button shows toast "Voice mode disabled. Text only communication is active."
- No verified round-trip: speak → transcript → LLM reply → spoken answer

---

## 4. MORNING BRIEF / ALARM — CODE EXISTS, NEVER PROVEN

- Android: `AlarmScheduler` (`setAlarmClock`, survives Doze), `BootReceiver` reschedules after reboot, `WakeUpActivity` full-screen over lock screen, max alarm volume, snooze button, sends `trigger: morning_alarm` over WS with device location if permitted
- Backend: 5:30 AM IST cron fires `morning_alarm_callback`; awake-verification workflow exists; night planning 10:30 PM
- **Never demonstrated end-to-end** (the backend was crash-looping until today, so no alarm ever reached the phone). The "brutal test" (force-stop, reboot, 3 consecutive mornings) is pending.

---

## 5. REMINDERS — PARTIAL

- Creating tasks/reminders by chat works through `task_manager.py` (rapidfuzz matching, interrupt() clarification for *missing* time)
- Delivery: APScheduler → WS broadcast (`asta_proactive`) → `ProactiveListenerService` notification + FCM push; reminders reload from Notion on backend restart
- **No AM/PM disambiguation**: "remind me at 7" is silently interpreted, never asks "7 AM or 7 PM?" (only task-name ambiguity is handled)
- **Notifications are text-only** — nothing is spoken. `synthesize_proactive_audio_b64` now exists server-side and `asta_proactive` carries `audio_base64`, but the phone only plays it if `ASTAForegroundService` is running (it isn't, ever, yet). `ProactiveListenerService` ignores the audio field.

---

## 6. MEMORY LAYER — DIRECT ANSWER: **wired and connected, but NOT "all set"**

**What's genuinely working:**
- All 4 layers connect and pass health checks: Redis (L1) → Neo4j Aura (L2) → Pinecone (L3, 384-dim MiniLM) → MongoDB (L4)
- `memory_engine` orchestrates writes (L4 durable first → L3+L2 parallel → L1 invalidate); prefetch worker starts
- Sessions persist and restore across backend restarts; LangGraph checkpointer (AsyncMongoDBSaver) works → multi-turn clarification works
- 99 vectors already in Pinecone from real usage

**What's NOT working for pattern/preference learning:**
1. L1.5 speculative prefetch has never worked (kwargs mismatch, error swallowed) — mid-sentence entity pre-warming is dead
2. CacheService datetime serialization errors on every session-cache write
3. spaCy model missing on server → entity extraction (PROJECT/SKILL/PERSON/GOAL...) degraded → the graph learns less than designed
4. Two Neo4j schemas still corrupting one Aura instance (l2_graph vs legacy graph_service)
5. **Pattern learning inputs are blocked on the phone**: Health Connect permission denied, Usage Stats not granted → `DailyMetricsWorker` (steps/sleep/screen-time every 30 min) posts nothing → ASTA cannot learn sleep/usage patterns yet
6. Preference learning ("calls me boss", tone, habits) exists only as static prompt personality — no explicit preference-extraction loop writes to Neo4j User node properties yet

**Bottom line:** the storage brain is alive; the *learning* loops that make it Jarvis are ~40% real. Fixes are itemized in the plan.

---

## 7. CHAT UI — FUNCTIONAL, PLAIN

- RecyclerView chat, text send works against `/api/chat`, online/offline indicator, silent-mode switch
- No glassmorphism, no voice-state visualization, mic button dead (disabled), stock Material styling

---

## 8. SECURITY / OFFLINE — MOSTLY IN PLACE

- Single-device binding (token + device ID) enforced on HTTP and WS ✔
- Token + device ID in EncryptedSharedPreferences (Keystore) ✔
- SQLCipher offline DB with sync_queue + `SyncWorker` batch upload ✔ (offline queueing untested end-to-end)
- Weak spots: bearer token also hardcoded as literals in 3 source files; HTTP plaintext transport

---

## SCORECARD vs. THE 10-ITEM DEFINITION OF DONE (ASTA_CONTEXT.md §7)

| # | Requirement | Status |
|---|---|---|
| 1 | Voice reminders fire reliably | 🟡 text notifications only, no voice, AM/PM gap |
| 2 | Wake word across the room | 🔴 one transform away (fix identified) |
| 3 | Silent mode toggle | 🟡 wired, unverified |
| 4 | 5:30 AM wake-up survives everything | 🟡 code exists, never demonstrated |
| 5 | Morning brief conversational | 🟡 backend flow exists, never delivered to phone |
| 6 | Task & habit management | 🟡 create/complete works by chat; streaks/slots partial |
| 7 | Research partner full loop | 🟡 engine + Notion exist, unverified this session |
| 8 | Offline fallback | 🟡 queue infra exists, untested |
| 9 | Pattern awareness v1 | 🔴 metrics blocked by permissions + server NLP degraded |
| 10 | Memory across sessions | 🟢 checkpointer + L4 verified working |
