# ASTA IMPLEMENTATION STATE — updated 2026-07-16 by gate-closer session

This file reflects only what the gate-closer session (2026-07-16) directly
verified. Every VERIFIED-LOCAL row below was proven by actually running the
cited script/test against real services (Groq, MongoDB Atlas, Neo4j Aura,
Redis) from this dev machine — not against a deployed/hosted ASTA server, so
each carries a "(server pending)" qualifier. Phases this session did not touch
are marked NOT RE-VERIFIED THIS SESSION and carry their last-known status
forward unchanged rather than being silently dropped or re-asserted.

## PHASE BOARD
Phase 0 (Environment/Imports/Boot): VERIFIED-LOCAL (server pending) — real
  import check + real uvicorn boot + `/api/health/` poll, proven to fail
  loudly when broken and to recover. `Makefile`, `scripts/verify.sh`.
Phase 1 (Pipecat Voice Pipeline / LLM Router): PARTIAL, VERIFIED-LOCAL for the
  parts exercised — real Groq STT transcript and real Groq chat completion
  both proven live. VAD/wake-word frame routing through the full pipecat
  transport graph was NOT driven this session (see scope note in
  `run_core_loop_live.py`'s module docstring).
Phase 2 (Wake Word): NOT RE-VERIFIED THIS SESSION. Last known: BROKEN (core
  pathing) per the 2026-07-15 audit.
Phase 3 (Memory Extraction / Graph Memory): VERIFIED-LOCAL (server pending) —
  real extraction LLM call, real Mongo write+read, real Neo4j/Graphiti
  write+read, real recall, recalled fact reflected in a real chat reply.
Phase 4 (Morning/Weather/News): NOT RE-VERIFIED THIS SESSION. Last known:
  BROKEN/STUBBED per the 2026-07-15 audit.
Phase 5 (Reminders): VERIFIED-LOCAL (server pending) — real schedule → real
  APScheduler fire on a shortened clock → real ack, against real Mongo.
Phase 6 (Habits/Reflection): NOT RE-VERIFIED THIS SESSION. Last known:
  BROKEN/STUBBED per the 2026-07-15 audit.
Phase 7 (Research): NOT RE-VERIFIED THIS SESSION. Last known: BROKEN/STUBBED
  per the 2026-07-15 audit. (This session did fix a cross-file test-pollution
  bug in its test file — see DECISIONS-MADE — but did not re-verify the
  service itself.)
Phase 8 (Dev Agent Gateway): VERIFIED-LOCAL (server pending) — all 5 required
  attack categories tested against the real gateway app.
Phase 9-10 (Offline Sync / Observability): NOT RE-VERIFIED THIS SESSION. Last
  known: MISSING per the 2026-07-15 audit.

Cross-cutting:
Verify pipeline: VERIFIED — proven to pass green, proven to fail loudly on a
  broken module (renamed import, real traceback, exit 1), proven to pass
  again after restoring.
Backup/Restore: VERIFIED-LOCAL — real Mongo + Neo4j dump, tarred, restored
  into scratch targets, canary record confirmed surviving the round trip in
  both stores.

## STATUS MATRIX
| Component | Status | Reason / evidence (file:line) | Disposition |
|---|---|---|---|
| `make verify` | VERIFIED | Real import check, real uvicorn boot + health poll, real pytest run; nonzero exit on any failure; proven both green and failing. `Makefile:8`, `scripts/verify.sh:41` (boot check), 44/44 pytest. | DONE |
| G1 boot | VERIFIED-LOCAL (server pending) | `/api/health/` → 200, no traceback in server log, on a locally started uvicorn instance. `scripts/verify.sh:41`. | DONE |
| G4 core loop | VERIFIED-LOCAL (server pending) | 7/7 steps against real Groq/Mongo/Neo4j, plus the bonus reminder check. `docs/verification/probes/run_core_loop_live.py:62` (step 1) through `:158` (step 7), `:179` (bonus). | DONE |
| Memory wire (voice → recall → prompt) | VERIFIED-LOCAL (server pending) | Real fact seeded via the real write path, real unpatched `recall()`, fact asserted inside the assembled system prompt. `docs/verification/probes/test_memory_voice_integration.py:16`. | DONE |
| Dev Agent Gateway security | VERIFIED-LOCAL (server pending) | All 5 required attacks (HMAC-tampered, nonce replay, path-jail escape, disallowed argv, kill-switch) tested against the real gateway app. `docs/verification/probes/test_gateway_security.py:50,66,91,39,116`. | DONE |
| Backup + restore | VERIFIED-LOCAL | Real Mongo (20 collections) + Neo4j (129 nodes/257 relationships at time of run) dumped, tarred, restored into scratch targets; canary survived in both. `scripts/backup.sh:37`. | DONE |
| Dependency pins (pipecat-ai, graphiti-core) | VERIFIED | Exact working versions pinned from `pip freeze` against the venv all of the above ran in. `requirements.txt:54,57` (`pipecat-ai[silero]==1.5.0`, `graphiti-core==0.29.2`). | DONE |
| Wake Word, Morning/Weather/News, Habits/Reflection, Research (service-level), Offline Sync, Observability | NOT RE-VERIFIED THIS SESSION | Out of scope for the gate-closer session; carrying forward the 2026-07-15 audit's last-known status (BROKEN/STUBBED/MISSING — see PHASE BOARD). | NEEDS A DEDICATED SESSION |

## DECISIONS-MADE
- Nothing is marked VERIFIED without a script or test that was actually run
  this session and cited above by file:line.
- Running the core loop for real (not against mocks) surfaced 5 latent
  production bugs that unit tests had mocked past; all root-caused and fixed
  (see `close2` commit message for the full list): `graph_ltm.initialize()`
  was never called anywhere; `graph_ltm.py` used a stale graphiti-core API
  (constructor args, `add_episode`/`search` signatures); Graphiti's default
  OpenAI dependency was swapped for Gemini (the project's `OPENAI_API_KEY` is
  a placeholder); `extractor.py` did `if not db_manager.db:`, which crashes
  against a real Motor connection; `LegacyLLMFactory.get_model()` pointed at
  a decommissioned Groq model; `db_manager.ObjectId` didn't exist, so
  `reminder_service`'s trigger/ack calls would `AttributeError` in production.
- A pre-existing test-isolation bug (`test_research_service.py` permanently
  poisoning `sys.modules['backend.app.core.llm_factory']`) was root-caused
  and fixed as part of making `make verify` genuinely green.

## NEXT STEP (exact)
Re-run G1 boot and the G4 core loop against a deployed/hosted ASTA instance
(not this local dev machine) to drop the "(server pending)" qualifier from
every VERIFIED-LOCAL row above. Separately, phases not touched this session
(2, 4, 6, 7, 9, 10) need their own dedicated verification pass — their status
above is carried forward from the 2026-07-15 audit, not re-checked now.

## VERIFY SNAPSHOT
- `make verify`: GREEN — 44/44 pytest, real import check, real boot check
  (`/api/health/` → 200). Proven to fail loudly when broken (renamed
  `backend/app/services/memory_orchestrator.py`, got a real traceback and
  exit 1) and to pass again after restoring.
- Core loop: 7/7, plus the bonus reminder check (set → fired on a shortened
  clock → acked), all against real services.
