# ASTA IMPLEMENTATION STATE — updated 2026-07-09T19:02:00Z by session 1
## PHASE BOARD
Phase 0: DONE
Phase 1: IN-PROGRESS
Phase 2–10: NOT-STARTED

## STATUS MATRIX
| Component | Guide ref | Status | Reason / evidence (file:line) | Disposition |
|---|---|---|---|---|
| settings_routes.py | I.3 | FIXED | `backend/app/api/settings_routes.py` uses `verify_bearer_and_device` | Fixed in Phase 0 |
| metrics_routes.py | I.3 | FIXED | `backend/app/api/metrics_routes.py` uses `verify_bearer_and_device` | Fixed in Phase 0 |
| routine_engine.py | I.3 | FIXED | `backend/app/workflows/routine_engine.py:118` IndentationError fixed | Fixed in Phase 0 |
| ws_transport.py | I.3 | FIXED | `backend/app/api/ws_transport.py` nested `ctx` fixed | Fixed in Phase 0 |
| WakeUpActivity.kt | I.3 | FIXED | View IDs and audioStreamer wired | Fixed in Phase 0 |
| memory_saga.py | I.3 | ATTIC | Imports removed, file deleted to attic | Fixed in Phase 0 |
| .env.template | I.3 | FIXED | Missing required config keys added | Fixed in Phase 0 |
| AstaNetworkClient.kt / ConfigManager.java | I.3 | FIXED | Ngrok fallbacks purged, using BuildConfig | Fixed in Phase 0 |
| LLM router | II | PARTIAL | `backend/app/core/llm_factory.py:4` exists but no quota ledger, no capability chains, single provider hardcoded | Rebuild in Phase 0/II |
| Pipecat Voice Pipeline | III.2 | MISSING | No `backend/app/voice/pipeline.py` or Pipecat integration | Build in Phase 1 |
| Reflex Processor | III.5 | MISSING | No filler pool or reflex layer | Build in Phase 1 |
| livekit-wakeword | IV.2 | MISSING | No `configs/asta.yaml` | Build in Phase 2 |
| Android Wake Word bug | IV.3 | PARTIAL | OpenWakeWord model integrated but feature normalisation buggy | Fix in Phase 2 |
| Session Extraction | V.4 | MISSING | No extraction call on session end; uses old transcript methods | Build in Phase 3 |
| Graphiti L2 | V.5 | MISSING | No Neo4j Aura Free or Graphiti setup | Build in Phase 3 |
| Morning System | VII.2 | PARTIAL | Alarm exists but no verified dead-man server check or verification | Build in Phase 4 |
| Jarvis Notification | VIII | MISSING | No delivery ladder, FCM integration incomplete | Build in Phase 5 |
| Proactive Engine | IX.2 | MISSING | No scheduler jobs for proactivity | Build in Phase 6 |
| Research Partner v2 | X | MISSING | No 4-section Notion page research pipeline | Build in Phase 7 |
| Dev Agent (Gateway v2) | XI.2 | MISSING | No `gateway/openclaw_gateway.py` hardened executor | Build in Phase 8 |
| PC Client | XII | MISSING | No PC tray client | Build in Phase 9 |
| Memory Explorer UI | XIII | MISSING | No timeline/graph UI | Build in Phase 10 |

## BLOCKED (needs Karthik)
- OPEN-1: Confirm EC2 billing status (Phase 0)
- OPEN-2: Need Karthik's 50 real clips for wake word training (Phase 2)
- OPEN-3: GPU model → decides ollama tag (Phase 8)
- OPEN-4: Key rotation confirmation before push (Phase 0)

## DECISIONS-MADE (deviations/choices, with reason)
- None yet.

## NEXT STEP (exact)
- Phase 1: Voice & Persona (Part III) — Integrate Pipecat pipeline, LLM Router, and Reflex processor.

## VERIFY SNAPSHOT
- make verify: P0 ✅
