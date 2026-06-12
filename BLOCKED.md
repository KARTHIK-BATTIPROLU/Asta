# BLOCKED — items needing Kartik's action

## Neo4j Aura instance unreachable (pre-existing, not caused by this build run)

**Item:** D2.5 acceptance test requires "Neo4j nodes + Pinecone vector grew" after a
research conversation. Pinecone confirmed growing (4 -> 5 vectors after the live
research test). Neo4j cannot be verified — the configured Aura instance does not exist.

**Exact error:**
```
Failed to connect to Neo4j: Cannot resolve address c706f89b.databases.neo4j.io:7687
```
`nslookup c706f89b.databases.neo4j.io` returns **Non-existent domain** (NXDOMAIN) —
this is not a sandbox/DNS restriction, the hostname itself no longer exists.

**What was tried:**
- Confirmed `.env` has `NEO4J_URI=neo4j+s://c706f89b.databases.neo4j.io`,
  `NEO4J_USERNAME=c706f89b`, `NEO4J_PASSWORD=...`, `NEO4J_DATABASE=c706f89b`.
- `nslookup` confirms NXDOMAIN — the Aura instance `c706f89b` appears to have been
  deleted or its free-tier instance expired/was removed.
- This is pre-existing (same error appears in logs before this session's changes).
- The system degrades gracefully as required: `memory.memory_engine` logs
  `L2_neo4j failed to connect` and continues with L1/L3/L4 only — no turn crashes.

**What Kartik must do:**
1. Create a new Neo4j Aura (free tier is fine) instance, or restart/restore the
   existing `c706f89b` instance from the Aura console if it was just paused
   (note: paused Aura instances usually still resolve DNS, so it was likely deleted).
2. Update `.env` with the new `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`,
   `NEO4J_DATABASE`.
3. Restart the backend — `memory.l2_graph` will reconnect automatically on next
   startup (no code change needed).

**Downstream impact:** None blocking. `research_context` is held in LangGraph thread
state (Mongo checkpointer) independent of Neo4j, so Day 3 content-chaining is NOT
affected. Memory recall (test #6) will work via L3 Pinecone + L4 Mongo even with L2
down, just without the entity-graph cross-linking.

## content_style_prefs.json is a PLACEHOLDER (Day 3, item 1)

**Item:** D3.1 requires `backend/preferences/content_style_prefs.json` built from
Kartik's real ChatGPT-derived style file. No such file was found anywhere in the
repo (only `linkedin_prefs.json` / `youtube_prefs.json` / `instagram_prefs.json`
existed, which are platform-specific, not the master style overlay).

**What was done:** Created `backend/preferences/content_style_prefs.json` as a
PLACEHOLDER following the schema the BLUEPRINT specifies (tone / structure / hooks /
hashtags / emoji / avoid / per_platform), seeded with reasonable first-principles
defaults consistent with the existing per-platform prefs files. It is marked
`"_placeholder": true` with a `"_note"` field. `content_manager.py` loads and merges
it with the platform-specific prefs file for every generation, and the
"remember this for my posts" voice-update path
(`preferences_service.update_from_voice("content_style", ...)`) writes directly into
this doc in Mongo (`preferences` collection, `type="content_style"`), so Kartik's
real preferences will naturally override the placeholder once he starts using it.

**What Kartik must do:** Either (a) say "remember this for my posts: ..." a few
times to organically build up `content_style_prefs` in Mongo, or (b) hand Claude
Code his real ChatGPT-derived style file and ask it to replace
`backend/preferences/content_style_prefs.json` with the real values (same schema).

## NOTE (not blocking): LangGraph 1.1.3 — second interrupt() in a resumed node

**Discovered during D3.4.** If a supervisor node calls `interrupt()` a SECOND time
during a RESUMED execution (i.e., the node was already resumed once via
`Command(resume=...)`, and hits a brand-new `interrupt()` further down), the
resulting checkpoint has `snap.interrupts` non-empty but `snap.next == ()`. A
THIRD invocation's `Command(resume=...)` then finds no resumable task and the
graph runs from an empty fresh state instead — producing an unrelated generic
response (confirmed via a standalone repro script against `debug-interrupt-test-2`,
both in-process and cross-process).

**Workaround used in `content_workflow`** (`backend/app/workflows/content_manager.py`):
only ONE `interrupt()` call total ("research first or raw?"). The
review/regenerate step is NOT a second `interrupt()` — instead the draft +
"looks good or want changes?" is returned as a normal response, with
`content_state["phase"] = "awaiting_review"` persisted on the thread (LastValue
channel). `classify_intent` short-circuits the next turn straight back to
`content_workflow` based on that phase. `run_supervisor_graph`'s resume-detection
was also loosened to `snap.interrupts` alone (was `snap.next AND snap.interrupts`),
since `snap.next` can't be trusted as the resumability signal.

**Latent same-class risk:** `task_manager._handle_reschedule` (around
`backend/app/workflows/task_manager.py:272-282`) has TWO sequential `interrupt()`
calls ("which task?" then "what time?") in one handler. If a single message
triggers BOTH (ambiguous task name AND no new time given), the second interrupt
may hit this same checkpoint issue on the next reply. Not fixed — out of scope for
Day 3 (pre-existing Day 1 code, "never refactor beyond task demands"), and likely
rare in practice (one ambiguity at a time is the common case). Flag for whoever
picks up the task_manager regression test in the final 9-test pass — if it fails,
apply the same phase-persistence pattern.
