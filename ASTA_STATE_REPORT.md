# ASTA State Report — July 6, 2026

## 1. Executive Summary
Following a comprehensive codebase audit of the ASTA personal assistant repository, the system is approximately 75% code-complete across backend services, the memory layer, and the mobile app. However, due to multiple critical runtime bugs, import errors, and compilation failures, only about 30% of the codebase is verified as working in isolation, and **0% is verified end-to-end**. The single biggest risk right now is that the backend API fails to start entirely due to a missing dependency module (`get_api_key` from `dependencies.py` imported by `settings_routes.py` and `metrics_routes.py`), combined with a syntax error in `routine_engine.py` and structural crash-loop bugs (such as `ctx.ctx` attribute errors) in the WebSocket loop of `ws_transport.py`. Furthermore, while the Android app compiles, its morning alarm activity lacks any audio-recording implementation, breaking the flagship awake-verification voice loop.

---

## 2. What Is Implemented AND Verified
The following components exist in the codebase and their basic imports, syntax, and unit-level dependencies have been validated:
* **Token Authentication & Device Binding**: Consolidated in [token_auth.py](file:///c:/Users/Karthik/OneDrive/Desktop/ASTA/backend/app/auth/token_auth.py). Enforces static token validation (`verify_bearer`) and device ID database validation (`verify_bearer_and_device`, `verify_ws_token_and_device`).
* **Android Encrypted Local Database**: SQLite database encrypted via SQLCipher (`AstaDatabaseHelper.kt`), loaded with a hardware-secured passphrase stored in `EncryptedSharedPreferences` (`SessionStore.kt`).
* **Android Alarm & Boot Hooks**: `AlarmScheduler.kt` uses `setAlarmClock()` for exact daily triggers at 5:30 AM IST. `BootReceiver.kt` successfully schedules the alarm on boot.
* **Basic Task Manager**: Conversational task CRUD and fuzzy-matching logic (`task_manager.py`) compiles and passes validation, though Notion database connection needs live infra.
* **STT/TTS REST Connectors**: Batch Deepgram transcription (`stt_service.py`) and MP3 speech synthesis (`tts_service.py`) are syntax-valid and ready.
* **L1.5 Speculative Prefetch Signature**: The kwargs mismatch and exception-swallowing bug in `l1_cache.py` has been fixed.

---

## 3. What Is Implemented But UNVERIFIED
These features have code implemented on both client and server, but require live infrastructure, API connections, or the physical device to test. 

To test these, Karthik must perform the following actions:
1. **Database & Memory Orchestration (L1/L2/L3/L4)**:
   * *Code status*: Code exists for Redis hot caching, Neo4j graph schemas (`l2_graph.py`), Pinecone vector operations (`l3_vectors.py`), and MongoDB Atlas cold store (`l4_store.py`).
   * *How to verify*: Ensure all databases are active, update `.env` credentials, and run the memory integration script:
     ```bash
     python memory/test_memory.py
     ```
2. **Notion Database Synchronizer**:
   * *Code status*: Full CRUD service wrapper in `notion_service.py` to synchronize tasks, habits, and research.
   * *How to verify*: Run the Notion connector check inside the `notion_tests` folder or execute a dummy task push from `python -c "from backend.app.services.notion_service import notion_service"`.
3. **FCM Push Notification Engine**:
   * *Code status*: Integrated on both Android (`AstaFcmService.kt`) and backend (`task_manager.py` using `firebase-admin`).
   * *How to verify*: Drop your Firebase `service-account.json` into `backend/secrets/` and trigger a test push via the metrics endpoint.
4. **Android Digital Wellbeing Snapshot Ingestion**:
   * *Code status*: WorkManager sync job (`DailyMetricsWorker.kt`) and `/api/wellbeing/snapshot` collection.
   * *How to verify*: Install the APK on a physical phone, grant `UsageStats` and `Health Connect` permissions, and watch logs for wellbeing snapshot submissions.

---

## 4. What Is Claimed But NOT Actually Implemented
The following claims in `ASTA_TODO.md` are incomplete or missing:
* **Phase 2.1 & 2.2: Awake Verification Conversation**: The TODO claims morning snooze and conversation loop are done. However, `WakeUpActivity.kt` on Android does **NOT** call `AudioStreamer.startRecording` at any point, meaning there is no way for the phone to record and stream Karthik's voice response back to the backend. The voice loop is non-existent.
* **Phase 3.2: Duplicate Cleanup**: The TODO claims that `memory_saga.py` has been retired. However, `memory_saga.py` is still actively imported in `main.py`, `session_manager.py`, and `memory_orchestrator.py`! It has not been retired or removed.
* **Phase 2.8: Research Partner Layout**: The TODO claims research is fully complete and organizes Notion pages into the 4-section layout defined in `ASTA_CONTEXT.md` §4.3 (HIS IDEA, FINDINGS, COMBINED SOLUTION, NEXT STEPS). Instead, `research_engine.py` hardcodes generic sections (`Executive Summary`, `Technical Deep Dive`, `Key Facts & Players`, `Sources & References`) and does not capture the user's initial context or angle.

---

## 5. What Is Genuinely Not Started
The following items remain unchecked on the backlog:
1. **Morning Wake-up Alarm Validation (E2E)**: The 3-morning consecutive test of the alarm firing after reboot/force-stop has not been performed.
2. **Offline Fallback Sync Engine (E2E)**: Simulating airplane mode, queuing multiple items on the phone, reconnecting, and verifying batch sync is unverified.
3. **Cross-session Memory Recency (L1/L3 transition)**: Compacting history and performing Neo4j cross-session recall under token limits.

---

## 6. Critical Findings

### Severity 1: Critical (Blocker)
1. **Server Startup Failure (Missing dependencies)**: `settings_routes.py` and `metrics_routes.py` import `get_api_key` from `backend.app.api.dependencies`, which does not exist in the repository. This causes a `ModuleNotFoundError` on server boot, preventing ASTA from starting.
2. **Morning Brief Workflow Compile Failure**: `routine_engine.py` has an `IndentationError` on line 119 immediately following an `if` block on line 118. Any attempt to trigger the morning briefing workflow crashes the python process.
3. **Barge-In and Connection Abort Crash Loops**: `ws_transport.py` contains multiple `ctx.ctx` and `ctx.ctx.ctx` references (e.g. lines 223, 327, 328, 364, 369, 370, 461, 472, 473) where it should simply access attributes directly on the `ctx` object. This causes immediate `AttributeError` exceptions during socket connection cleanup, abort events, or barge-in interruptions.
4. **Broken Real-Time STT Connection**: In `ws_transport.py` line 222, the code calls `asyncio.create_task(start_ctx.stt_stream())` but the function name is `start_stt_stream()`. This raises a `NameError` in the background and locks `ctx.stt_stream` to `True` (a boolean), breaking the real-time speech streaming pipeline and forcing a fallback to REST-based batch transcription.
5. **WakeUpActivity UI Buttons Unregistered**: `WakeUpActivity.kt` refers to layout IDs `R.id.btnSnooze` and `R.id.btnAwake` during `handleAwake()`, but these buttons are created programmatically in `onCreate()` and are never assigned these IDs. This will prevent the activity from updating buttons when the user acknowledges the alarm.

### Severity 2: Medium (Functional Defect)
1. **Legacy Saga Import Leak**: `memory_saga.py` is still actively imported in the core path despite memory operations migrating to `memory_engine.py`.
2. **Notion Research Layout Mismatch**: Section layouts created in Notion by `research_engine.py` do not match the Jarvis specification in `ASTA_CONTEXT.md`.
3. **Missing Environment Variables**: `.env.template` is missing 15 key variables that the backend configuration (`config.py`) expects, including critical ones like `ASTA_API_BEARER_TOKEN`, `REDIS_URL`, `NOTION_API_KEY`, and `SERPER_API`.
4. **Android Client Hardcoded URL**: `AstaNetworkClient.kt` and `ConfigManager.java` contain hardcoded placeholder ngrok URLs (`tapioca-pelican-sarcasm`) as fallback constants.

---

## 7. The Next 5 Actions

### Action 1: Fix Settings and Metrics Import Errors
* **File to change**: [settings_routes.py](file:///c:/Users/Karthik/OneDrive/Desktop/ASTA/backend/app/api/settings_routes.py) and [metrics_routes.py](file:///c:/Users/Karthik/OneDrive/Desktop/ASTA/backend/app/api/metrics_routes.py).
* **Fix**: Replace `Depends(get_api_key)` with `Depends(verify_bearer_and_device)` from `backend.app.auth.token_auth` to protect settings/metrics via token+device auth. Delete the broken dependencies import.
* **Verification**: Run `python -c "import backend.app.main"` and confirm it loads without throwing `ModuleNotFoundError`.

### Action 2: Fix Routine Engine Indentation Syntax Error
* **File to change**: [routine_engine.py](file:///c:/Users/Karthik/OneDrive/Desktop/ASTA/backend/app/workflows/routine_engine.py).
* **Fix**: Properly indent or resolve the dangling `if` block at line 118:
  ```python
  if step_name in ["CALENDAR_TODAY", "NOTION_TASKS"]:
      pass  # or add the appropriate logging/logic
  ```
* **Verification**: Run `python -m py_compile backend/app/workflows/routine_engine.py` and confirm it compiles with exit code 0.

### Action 3: Resolve ws_transport.py Attribute and Name Errors
* **File to change**: [ws_transport.py](file:///c:/Users/Karthik/OneDrive/Desktop/ASTA/backend/app/api/ws_transport.py).
* **Fix**: 
  1. Replace all occurrences of `ctx.ctx.` and `ctx.ctx.ctx.` with `ctx.`.
  2. In line 222, replace `start_ctx.stt_stream()` with `start_stt_stream()`.
* **Verification**: Test WebSocket connection on backend mock endpoints to ensure no AttributeErrors occur on connection disconnect/abort.

### Action 4: Wire Audio Recording to Android WakeUpActivity
* **File to change**: `WakeUpActivity.kt`.
* **Fix**: In `handleAwake()`, call `audioStreamer?.startRecording { audioChunk -> wsClient?.sendAudio(audioChunk) }` to open the microphone channel and stream user voice responses back to the server for the verification dialogue.
* **Verification**: Verify that the microphone records and streams packets during the wake-up activity using adb logcat.

### Action 5: Complete Environment Variable Template
* **File to change**: [.env.template](file:///c:/Users/Karthik/OneDrive/Desktop/ASTA/.env.template).
* **Fix**: Add all missing keys that the backend requires for startup (specifically `ASTA_API_BEARER_TOKEN`, `REDIS_URL`, `NOTION_API_KEY`, `ANTHROPIC_API_KEY`, `SERPER_API`, etc.).
* **Verification**: Delete `.env`, copy `.env.template` to `.env`, set mock values, and confirm server runs without configuration warnings.

---

## 8. Definition of Done Scoreboard

| DOD Item | Status | Notes |
|---|---|---|
| 1. Voice reminders fire | 🟡 code-ready un-verified | Requires live Redis/Mongo & FCM connection. |
| 2. Wake word works | 🟡 code-ready un-verified | OpenWakeWord ONNX code present in APK, needs physical check. |
| 3. Silent mode toggle | ❌ not working | Blocked by missing `get_api_key` import bug on backend. |
| 4. 5:30 AM alarm survives | ❌ not working | Android UI button IDs mismatch; lacks microphone recording. |
| 5. Morning brief is conversational | ❌ not working | Blocked by python syntax/indentation error in `routine_engine.py`. |
| 6. Task & habit management | 🟡 code-ready un-verified | Blocked by `routine_engine.py` syntax error for streaks. |
| 7. Research partner full loop | 🟡 code-ready un-verified | Logic exists, but Notion page section layouts do not match spec. |
| 8. Offline fallback | 🟡 code-ready un-verified | Encrypted SQLite database helper ready. |
| 9. Pattern awareness v1 | 🟡 code-ready un-verified | snapshot ingestion endpoints exist, needs live data feed. |
| 10. Memory works across sessions | 🟡 code-ready un-verified | Merged retrieval RAG flow compiles, needs live aura/pinecone. |
