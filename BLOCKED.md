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

## D5.3 memory recall via `other_workflow` is ungrounded / inconsistent (downstream of the Neo4j outage above)

**Item:** D5.3 requires 3 themed conversations (separate sessions) -> a recall
question in a brand-new session whose answer contains the SPECIFIC facts from
those conversations, plus a Notion link.

**What was tried (all via live `/api/chat`, backend on :8000):**
1. Ran 3 themed conversations (`mobile-proof-1/2/3`):
   - "my secret project codename is Project Solstice ... launch date August 15th"
   - "Add a task: email the Solstice deck to Priya by Friday 5pm" -> correctly
     created a real Notion Routine row (see link below).
   - "I take my coffee with oat milk and no sugar ... best coding after 9pm"
   - Verified the WRITE path: Pinecone `asta-memory-v2` vector count went
     23 -> 26 (one per turn), Mongo L4 logged "Session ... saved successfully"
     for all three.
2. Recall attempt 1 (`mobile-proof-recall`): `classify_intent` labelled the
   recall question "routine" (LLM classify, no keyword match) -> routed to
   `task_manager`, which just listed today's tasks and never saw
   `memory_context` at all (only `other_workflow` injects it). FIXED the
   classify prompt in `backend/app/core/supervisor_graph.py` (clearer
   routine/other definitions + examples) and restarted the backend — verified
   via server.log the recall question now classifies as "other" and reaches
   `other_workflow`.
3. Recall attempt 2 (`mobile-proof-recall2`, generic phrasing): now reaches
   `other_workflow`, `get_context_for_session` retrieved 3 sessions / 616
   chars of "RELEVANT PAST CONTEXT" — but the answer ("codename Eclipse",
   "Q3 2026", "coffee black with cinnamon", "9-11am") matches NONE of my
   facts. The 3 retrieved sessions are older pre-Day5 memory entries, not
   `mobile-proof-1/3`.
4. Recall attempt 3 (`mobile-proof-recall3`, mentioning "Project Solstice" by
   name + "remind me what I said"): "remind" hit `ROUTINE_KEYWORDS`, routed
   back to `task_manager`, which started creating a NEW reminder titled
   "Remind about Project Solstice details" and is paused on an interrupt
   asking for a time. Left as an abandoned thread (no Notion row created —
   the interrupt fires before `notion_service.create_task`).
5. Recall attempt 4 (`mobile-proof-recall4`, "Project Solstice" by name,
   keyword-safe phrasing): reached `other_workflow` again, but this time
   `get_context_for_session` returned **0 sessions** (verbatim term match,
   yet nothing retrieved) -> empty `memory_context` -> the LLM fabricated a
   THIRD different answer ("codename Luminari", "Q4", "coffee black",
   "9am-1pm").

**Root cause:** `memory_engine.get_context_for_session` only does
entity/cluster-filtered L2+L3 retrieval when Neo4j (L2) is reachable (see the
Neo4j entry above — `c706f89b.databases.neo4j.io` is NXDOMAIN). With L2 down,
`spotted` entities is always `[]`, so it always falls through to the generic
branch: `l3_vectors.search_by_text(user_input, top_k=MEMORY_TOP_K_SESSIONS)`
over the WHOLE Pinecone index with no relevance filter. This generic fallback
is inconsistent (3 unrelated sessions one time, 0 sessions for a verbatim term
match the next) and `other_workflow`'s "quick" LLM model fabricates a
confident-sounding answer when the injected context doesn't answer the
question, instead of saying "I don't have that on record."

**What was NOT changed (out of "smallest change" scope):**
`entity_extractor` summary quality, `l3_vectors.search_by_text` ranking/top_k,
and `other_workflow`'s prompt grounding/refusal behavior. These are
cross-cutting memory-pipeline changes, not a Day-5-sized fix.

**What Kartik must do:**
1. Primary fix is the SAME as the Neo4j entry above — restore the Neo4j Aura
   instance so entity/cluster-filtered retrieval runs again. This is very
   likely to fix recall precision (the generic full-index fallback is the
   unreliable path).
2. If recall is still weak after Neo4j is restored, consider separately:
   tightening `other_workflow`'s system prompt to refuse ungrounded recall
   ("if it's not in the context below, say you don't have it") so failures
   are honest instead of fabricated, and check that
   `entity_extractor.extract()`'s summaries retain named entities like
   project codenames.

**What WAS verified and DOES work (Day 5 acceptance evidence):**
- Memory WRITE path for all 3 themed conversations (Pinecone count +3, Mongo
  L4 saves all logged).
- The task-creation conversation produced a real Notion Routine DB row:
  "[MEDIUM] email the Solstice deck to Priya" —
  https://app.notion.com/p/MEDIUM-email-the-Solstice-deck-to-Priya-37e337e75d1781708157ed31d75537c2
  (archived as test data per D5.4).
- The classify_intent fix is a real, verified improvement: general
  questions/statements now correctly reach `other_workflow` (confirmed via
  server.log `[classify_intent] ... -> other`), which they did not before.

## UPDATE — 3 real bugs found + fixed in the memory pipeline; recall still blocked, but now by quota exhaustion (not crashes)

**Follow-up investigation found the recall failure above was not (only) the
generic-fallback-relevance issue originally diagnosed — it was compounded by
THREE separate bugs that were silently destroying session summaries before
they ever reached Pinecone/Mongo. All three are now fixed:**

1. **`memory/l3_vectors.py` crash on list-type `topics` metadata** —
   `search_by_text`/`search_by_entity` did `match.metadata.get("topics", "").split(",")`,
   but `memory_saga` writes `topics` as a real `list`, not a comma-string.
   `.split(",")` on a list raised `AttributeError`, caught by the function's
   blanket `except`, returning `[]` — i.e. **every** semantic search silently
   returned zero results whenever the matched vector came from `memory_saga`.
   Fixed with a `_parse_topics()` helper that accepts both list and string.
   Verified: post-fix, `L3 search returned 3 results` for a query that
   previously crashed to 0.

2. **`memory/entity_extractor.py` had no LLM fallback** — it built its own
   `ChatGroq(model="llama-3.3-70b-versatile")` directly. When Groq's TPD limit
   is hit (see below — this is now the NORMAL state, not an edge case), the
   call raises, and the `except` branch returns
   `{"summary": "Extraction failed - unknown error.", "entities": [], "topics": []}`.
   **This placeholder string is what gets embedded and stored as the session's
   summary** — permanently breaking recall for that session regardless of
   Neo4j status. This is confirmed to be exactly what happened to
   `mobile-proof-1/2/3`: all three have `summary="Extraction failed - unknown
   error."` in Mongo L4, so their embeddings represent the error string, not
   "Project Solstice" / coffee prefs / etc. **They cannot be recovered** — the
   original conversation content was never embedded.
   Fixed: `entity_extractor.extract()` now calls
   `backend.app.core.llm_factory.acomplete(..., task="generate", ...)`
   (Groq primary, Gemini fallback) instead of a raw Groq client.

3. **`memory/memory_saga.py` had the same pattern** — its own
   `self.groq_client = AsyncGroq(...)` for `_extract_entities` (topics +
   Neo4j relationships). Its failure fallback was milder (preserves the real
   TextRank summary, just sets `topics=["general"]`), but it was still a
   silent Groq-only path with no fallback. Fixed the same way: routed through
   `llm_factory.acomplete(..., task="generate", max_tokens=2000)`, dropping
   the Groq-specific `response_format={"type": "json_object"}` (the existing
   prompt already demands JSON-only and the code already strips ``` fences).

4. **Bonus bug found while testing #2/#3**: `llm_factory._try_gemini` hardcoded
   `gemini-1.5-flash`, which now 404s ("model not found") for this API key —
   so the "Gemini fallback" was **never actually working**, for ANY caller,
   this whole project. Tried `gemini-2.0-flash` next — that model has a hard
   `limit: 0` on this key's free tier. `gemini-2.5-flash` is the only model
   that actually responds (confirmed via direct test). Fixed
   `llm_factory.py` to use `gemini-2.5-flash`.

**Verified working end-to-end**: after restarting with all 4 fixes, the
startup session-finalization batch (`day4-reminder-test-*`) logged
`MemorySaga - INFO - Entity extraction successful for day4-reminder-test-...`
**twice** — Groq 429'd, Gemini 2.5-flash fallback succeeded, real
topics/relationships were extracted. This is the first time this path has
worked in the entire project (point 4 means Gemini fallback was dead before).

**Why a fresh "Project Aurora" recall demo could NOT be completed right now**:
immediately after the above success, I ran two new themed test turns
(`memory-fix-verify-1`, `memory-fix-verify-2` — "secret project codename is
Project Aurora, launch Oct 1st, tea with honey no milk") to replace the
unsalvageable `mobile-proof-*` sessions. Both hit:
```
Groq: 429 TPD limit 100000, Used ~99768-99949  (org_01k1be0wdbe0c86tpaqq4thya1, llama-3.3-70b-versatile)
Gemini: 429 Quota exceeded for generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash
```
i.e. **both providers' daily quotas for the `generate` task are now
exhausted simultaneously** — Groq's has been pinned at ~99.6-100% of its
100k TPD for this entire project session (this is a chronic, project-wide
ceiling, not specific to memory), and Gemini's 20/day free-tier quota (a very
small allowance) got used up by the finalization-batch retries + my fixes'
own fallback calls. So `memory-fix-verify-1/2` ALSO ended up with placeholder
summaries (`"Extraction failed - JSON parse error."` — a different, but
equally unsalvageable, placeholder) — joining `mobile-proof-1/2/3` as test
sessions that need to be superseded once quota is available.

**What Kartik must do (new, in addition to Neo4j + content_style_prefs
below):**
1. The CODE is now correct — Groq→Gemini fallback works end-to-end (proven).
   Nothing more to fix here without changing model/tier policy.
2. Once either quota has headroom, re-run the "Project Aurora" style themed
   conversation + a recall question in a new session to get the final D5.4
   acceptance evidence (real summary in Mongo, recall answer mentions
   "Project Aurora"/"Oct 1st"/"tea with honey no milk"). The code path is
   ready; it just needs one clean LLM call to land.

## ROOT CAUSE FOUND + FIXED: the chronic Groq TPD exhaustion was a self-inflicted infinite retry loop

While investigating why Groq's `llama-3.3-70b-versatile` TPD sits at ~99.6-100%
of its 100k/day limit *constantly* (not just during heavy use — it was pinned
there even right after a fresh restart with zero user activity), found:

- `session_manager`'s background batch processor runs every
  `BATCH_INTERVAL_SECONDS=5`, and `_fetch_finalizing_batch` re-selects ANY
  session with `status in {finalizing, partial_sync, pending_vector}` whose
  `updated_at` is more than `RESUME_GRACE_SECONDS=45` old.
- Any session where `MemorySaga.execute()` returns `False` gets
  `status="partial_sync"`. Since Neo4j (`c706f89b...`) is permanently
  NXDOMAIN, `_write_neo4j` ALWAYS raises, so `saga_ok` is ALWAYS `False` for
  every session — they NEVER reach `status="completed"`.
- Net effect: the same handful of `day3-`/`day4-*-test-*` sessions were being
  re-finalized roughly every 45 seconds, FOREVER, since the Neo4j outage
  began. Each re-finalization called `MemorySaga._extract_entities()`, which
  called `graph_service.get_existing_nodes()` (fails, silently returned `{}`
  before this fix) and then **still made a full Groq `llama-3.3-70b-versatile`
  completion call anyway** — whose output would be discarded seconds later
  when `_write_neo4j` raised regardless.
- That's a wasted ~500-2500 token `generate` call roughly every 45 seconds,
  24/7, since Neo4j went down — easily enough to permanently saturate a 100k
  TPD budget and explains why EVERY `task="generate"` call project-wide
  (chat replies, research, content) has been fighting for scraps of the same
  pool this whole session.

**Fixed** (`memory/graph_service.py` + `memory/memory_saga.py`):
`get_existing_nodes()` now returns `None` on a Neo4j connection failure
(previously returned `{}`, indistinguishable from "connected, empty graph").
`_extract_entities()` checks for `None` and skips the LLM call entirely,
returning the existing graceful fallback (`topics=[]`, real `summary`
preserved) — Mongo/Pinecone writes still happen normally, only the
Neo4j-only entity/relationship extraction is skipped. Verified post-restart:
log now shows `MemorySaga - WARNING - Neo4j unreachable - skipping entity
extraction for day4-...` with **zero** Groq/Gemini calls in that batch
(previously: `httpx POST .../groq.com 429` + Gemini fallback every cycle).

**Self-healing**: this fix doesn't require Kartik to do anything — it just
stops adding new waste. Groq's 100k TPD is a rolling window, so it will
gradually recover now that nothing is burning ~500-2500 tokens every 45s for
no reason. Once Neo4j IS restored (see entry above), `get_existing_nodes()`
naturally starts returning real data again and entity extraction resumes
automatically — no further code change needed.

3. Gemini's `gemini-2.5-flash` free tier is only 20 requests/DAY — thin as a
   fallback, but with the drain above fixed, Groq should rarely need it.
   Optional: enable billing on the Gemini key for headroom, but likely
   unnecessary now.
