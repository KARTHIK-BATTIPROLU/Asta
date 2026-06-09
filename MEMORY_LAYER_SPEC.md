# ASTA Memory Layer — Complete Technical Specification

> Reverse-engineered blueprint of the memory subsystem of the ASTA personal
> assistant, written so it can be rebuilt standalone in another application.
> All file paths are relative to the repo root.

---

## 0. IMPORTANT: there are two memory implementations

While documenting, be aware the repo contains **two overlapping memory
subsystems that share the same backing stores** (MongoDB, Pinecone, Neo4j, the
MiniLM embedding model, and Groq for extraction). They evolved separately and
were never fully merged.

| | **System A — `memory_engine` (5-layer)** | **System B — `MemorySaga` + orchestrator (3-phase)** |
|---|---|---|
| Entry point | `from memory import memory_engine` | `memory.memory_saga.MemorySaga`, `memory.memory_orchestrator` |
| Master file | `memory/memory_engine.py` | `memory/memory_saga.py`, `memory/memory_orchestrator.py` |
| Mongo DB name | `asta_db` (`settings.DB_NAME`) | `asta_memory` (hardcoded) |
| Mongo collections | `sessions`, `permanent_memory`, `entities`, `content_logs` | `sessions`, `pending_confirmations` |
| Neo4j root label | `User {name:"Karthik"}` | `Person {name:"Karthik"}` |
| Neo4j rels | `HAS`, `COVERS`, `RELATED_TO` | `HAS_CATEGORY`, `CONTAINS`, `RELATED_TO`, `TOUCHES_PROJECT`, `USES_SKILL`, `INVOLVES_TOOL`, … |
| Summary | Groq LLM (3–5 bullets) | `summa` TextRank (extractive, ≤300 chars) + Groq for entities |
| Write trigger | session end (`save_session`) | L1 token overflow + session end (Outbox/saga) |
| Read fusion | per-entity cluster→vector→fetch | Reciprocal Rank Fusion (RRF, k=60) |
| Wired into | supervisor graph, session_manager, chat, research graph | WebSocket routes, L1-overflow pipeline, retry worker |

**Recommendation for the rebuild:** adopt **System A's layered model** (it is the
"single memory brain" the rest of the app imports and the backend orchestrator
explicitly delegates to — see `backend/app/services/memory_orchestrator.py:137`),
and fold in **System B's strongest ideas** (the Outbox/saga write with a retry
worker, confidence-gated entity confirmation, and RRF fusion on read). The two
schemas should be unified into one. The rest of this document describes both but
treats System A as the canonical architecture.

---

## 1. OVERVIEW

### 1.1 What it does / problem it solves

The memory layer gives a stateless LLM assistant **durable, cross-session, long-term
memory** about a single user ("Karthik"). It solves four problems:

1. **Conversation amnesia** — the raw LLM has no memory beyond its context window.
   This layer persists every session and recalls relevant past sessions on demand.
2. **Latency** — naive RAG over a vector DB is slow for a *voice* assistant. The
   design adds a Redis hot cache and a speculative **prefetch engine** so that by
   the time the user finishes talking, relevant context is already in RAM.
3. **Identity / structured knowledge** — beyond "what was said," it maintains a
   **knowledge graph** of who the user is: their projects, skills, tools, people,
   interests, and commitments, and which sessions touched each.
4. **Token budget** — it compresses sessions into short summaries + embeddings so
   that recall injects a few hundred tokens, not whole transcripts.

### 1.2 High-level architecture (text diagram)

```
                         ┌─────────────────────────────────────────────┐
   user turn  ─────────► │  L0  LangGraph state  (in-flight, per-turn)  │
                         │      thread_id = session_id, checkpointed     │
                         └───────────────┬─────────────────────────────┘
                                         │ retrieve on turn start
                                         ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  L1   Redis hot cache              memory/l1_cache.py                   │
   │       • active_session:{sid}       (TTL 1h)                             │
   │       • entity_ctx:{entity}        (TTL 24h)  ← filled by prefetch      │
   │       • retrieved_ctx:{sid}        (TTL 1h)                             │
   └───────────────┬───────────────────────────────────────────┬──────────┘
       cache miss  │                                  prefetch   │ (background)
                   ▼                                             ▼
   ┌───────────────────────────┐                  ┌──────────────────────────────┐
   │ L1.5 Prefetch engine       │  spots entities  │  speculative fan-out:         │
   │ memory/prefetch_engine.py  │ ───────────────► │  L2 cluster → L3 vec → L4 doc │
   └───────────────────────────┘                  └──────────────────────────────┘
                   │
   READ pipeline   │  spot entities → for each entity:
                   ▼
   ┌────────────────────────────┐   session_ids   ┌────────────────────────────┐
   │ L2  Neo4j knowledge graph   │ ──────────────► │ L3  Pinecone vector store   │
   │ memory/l2_graph.py          │  (cluster, 2-hop)│ memory/l3_vectors.py        │
   │ entities + relationships    │ ◄────────────── │ 384-d MiniLM, cosine        │
   └────────────────────────────┘   filter ids     └─────────────┬──────────────┘
                                                       top-k ids   │
                                                                   ▼
                                              ┌────────────────────────────────┐
                                              │ L4  MongoDB cold store          │
                                              │ memory/l4_store.py              │
                                              │ full sessions, summaries,       │
                                              │ permanent memory, entities      │
                                              └────────────────────────────────┘

   WRITE pipeline (session end): extract entities (Groq) → L4 (full doc) →
   ║ parallel ║ → L3 (summary vector) + L2 (entities + session links) → L1 cleanup
```

System B adds an **Outbox/Saga** variant of the write: MongoDB is the commit
point (`embedding_status / neo4j_status = "pending"`), then Pinecone and Neo4j are
written and flipped to `"complete"`; a background `SagaRetryWorker` retries any
that stayed pending (polls every 30s, exponential backoff, dead-letter after 3).

---

## 2. STORAGE

### 2.1 Stores used and why

| Layer | Store | Library | Role | Why this store |
|------|-------|---------|------|----------------|
| L0 | LangGraph checkpointer (Postgres / MongoDB / in-mem `MemorySaver`) | `langgraph-checkpoint-*` | per-thread conversation state, interrupt/resume | needed for multi-turn clarification & crash recovery |
| L1 | **Redis** | `redis.asyncio` (`redis==5.1.0`, `hiredis`) | ephemeral hot cache | sub-ms reads; TTL eviction; perfect for "feels instant" voice UX |
| L2 | **Neo4j (Aura)** | `neo4j` async driver | knowledge graph: entities + relationships | relationship traversal ("everything related to ASTA within 2 hops") is native and cheap; impossible to do well in a doc store |
| L3 | **Pinecone (serverless)** | `pinecone` | semantic vector search over session summaries | managed ANN; metadata filtering by `session_id` to combine with graph |
| L4 | **MongoDB (Atlas/local)** | `motor` (async) + `pymongo` | durable cold store: full sessions, summaries, permanent memory, entity registry | flexible schema, TTL indexes for transcript expiry, cheap durable storage |

### 2.2 Data models / schemas

#### MongoDB — `sessions` (System A, DB `asta_db`) — `memory/l4_store.py`
```jsonc
{
  "session_id": "string (UNIQUE index)",
  "workflow_type": "research | routine | chat | general | ...",
  "start_time": "ISO datetime string",
  "end_time": "ISO datetime string",
  "summary": "string (3-5 bullets, Groq-generated)",
  "entities": [
    { "name": "ASTA", "entity_type": "PROJECT", "description": "...", "confidence": 0.95 }
  ],
  "topics": ["string", "..."],
  "embedding_id": "string (Pinecone vector id, == session_id)",
  "notion_page_id": "string (optional)",
  "raw_transcript": [ { "role": "user|assistant", "content": "..." } ],
  "raw_transcript_expires_at": "datetime  ← TTL index, default +90 days"
}
```
Indexes: `session_id` unique; `workflow_type`; `entities.name`; `end_time`;
TTL on `raw_transcript_expires_at` (expireAfterSeconds=0).

#### MongoDB — `sessions` (System B, DB `asta_memory`) — `memory/memory_saga.py`
```jsonc
{
  "session_id": "string",
  "user_id": "KARTHIK",
  "timestamp": "ISO", "ended_at": "ISO", "duration_seconds": 0,
  "summary": "string (TextRank, ≤300 chars)",
  "topics": ["..."],
  "tool_calls": ["Notion", "Serper Search"],
  "message_count": 0,
  "raw_messages": [ { "role": "...", "content": "..." } ],
  "embedding_status": "pending | complete",   // Outbox state machine
  "neo4j_status":     "pending | complete",
  "status":           "completed | partial_sync",
  "summary_hash": "sha256 (used for dedup detection)",
  "importance_score": 0.0,                     // 0.4*msg + 0.4*recency, *1.5 if pinned
  "created_at": "ISO"
}
```

#### MongoDB — `permanent_memory` — explicit "remember this" facts
```jsonc
{
  "memory_id": "uuid4 (UNIQUE)",
  "content": "string",
  "tags": ["array (indexed)"],
  "date_stored": "ISO",
  "recalled_count": 0          // incremented each recall
}
```

#### MongoDB — `entities` — deduplicated entity registry
```jsonc
{
  "name": "ASTA",
  "entity_type": "PROJECT",     // unique compound index (name, entity_type)
  "description": "string",
  "confidence": 1.0,
  "last_seen": "ISO"
}
```

#### MongoDB — `pending_confirmations` (System B) — entities awaiting user approval
```jsonc
{
  "confirmation_id": "uuid4",
  "session_id": "string",
  "entity_type": "project|skill|person|interest|...",
  "entity_data": { "name": "...", "confidence": "MEDIUM", "reason": "..." },
  "confidence": "MEDIUM | LOW",
  "status": "awaiting_karthik | approved | rejected",
  "created_at": "ISO"
}
```

#### MongoDB — `preferences` — user facts/preferences — `backend/app/services/preferences_service.py`
```jsonc
{ "type": "linkedin|youtube|instagram|news|routine|personality", "...": "arbitrary fields" }
```

#### Pinecone — `asta-memory` index
- **dimension 384**, **metric cosine**, serverless (AWS `us-east-1`).
- Vector `id == session_id` (or `permanent_{memory_id}`).
- `values` = MiniLM embedding of the **summary**.
- `metadata`: `{ session_id, workflow_type, end_time, topics (csv string), entity_names (csv string), summary_snippet (≤200 chars) }`.

#### Neo4j — knowledge graph

System A (`memory/l2_graph.py`, `memory/schema.py`):
```
(:User {name:"Karthik", current_focus, last_active})
  -[:HAS]->     (:Project|:Skill|:Person|:Goal|:Topic|:Decision|:Task {name, description, created_at, last_seen})
(:Session {session_id, workflow_type, summary, created_at})
  -[:COVERS]->  (entity)
(entity)-[:RELATED_TO]->(entity)         // entity-to-entity, up to depth hops
```
Indexes: one per entity label on `.name`.

System B (`memory/graph_service.py`, `memory/schema_init.py`) — richer identity tree:
```
(:Person {name:"Karthik"})
  -[:HAS_CATEGORY]-> (:Category {name:"Skills|Projects|Tools|People|Interests|Commitments"})
(:Category {name:"Skills"})
  -[:CONTAINS]-> (:SkillGroup {name:"Programming Languages|Frameworks|Databases|Dev Tools|AI & ML"})
  -[:CONTAINS]-> (:Skill {name:"Python|FastAPI|MongoDB|Neo4j|Pinecone|Groq"})
(:Category {name:"Projects"}) -[:CONTAINS]-> (:Project {name:"ASTA"})
(:Category {name:"Tools"})    -[:CONTAINS]-> (:Tool {name:"Notion|Google Calendar|Serper Search|Weather|Gemini"})

(:Session {session_id, timestamp, ended_at, duration_seconds, summary, topics[],
           tool_calls[], message_count, pending_confirmations[]})
  -[:RELATED_TO]->        (:Person)
  -[:TOUCHES_PROJECT]->   (:Project)
  -[:USES_SKILL]->        (:Skill)
  -[:INVOLVES_TOOL]->     (:Tool)
  -[:INVOLVES_PERSON]->   (:User)
  -[:CREATES_COMMITMENT]->(:Commitment)
```
Constraints: uniqueness on `Session.session_id`, `Person.name`, `Project.name`,
`Skill.name`, `Tool.name`. **All writes use `MERGE`, never `CREATE`** — this is
the deduplication guarantee.

### 2.3 Short-term vs long-term separation

| | Short-term (volatile) | Long-term (durable) |
|---|---|---|
| Where | L0 LangGraph state; L1 Redis; L1 in-mem deque (`memory/l1_session.py`, 2000-token window) | L2 Neo4j, L3 Pinecone, L4 MongoDB |
| Lifetime | turn / session; Redis TTLs (1h hot, 24h entity) | permanent (raw transcripts TTL'd at 90 days; summaries/graph kept) |
| Trigger to promote | session end, or L1 token overflow (>2000) | — |

The boundary is the **write pipeline**: when a session ends (or L1 overflows),
short-term content is summarized, embedded, entity-extracted, and pushed into the
three long-term stores.

---

## 3. MEMORY TYPES

### 3.1 Conversational / episodic memory (chat history)
- **Raw transcript:** `sessions.raw_transcript` / `raw_messages` in MongoDB,
  auto-expiring after `SESSION_TRANSCRIPT_TTL_DAYS = 90`.
- **Episodic summary:** the `summary` field (compressed) + its Pinecone vector.
  This is what gets recalled and injected — never the raw transcript.
- **In-flight window:** `memory/l1_session.py` keeps a `deque` of the live turns
  with a 2000-token cap; overflow promotes older turns to long-term.

### 3.2 Semantic / factual memory (user facts, preferences)
Three distinct stores:
1. **Knowledge graph (Neo4j)** — structured facts about the user: Projects,
   Skills, Tools, People, Interests, Commitments, plus `User.current_focus`.
2. **`permanent_memory` (Mongo)** — free-text facts the user explicitly asks to
   remember, tagged; recall is tag- + vector-based (`memory_engine.remember/recall`).
3. **`preferences` (Mongo)** — typed preference docs (linkedin/youtube/news/…)
   updated from natural language via an LLM that emits a JSON patch
   (`preferences_service.update_from_voice`).

### 3.3 Embeddings / vector storage
- **Model:** `sentence-transformers/all-MiniLM-L6-v2`, **384-dim**, cosine.
- Loaded **once at import** (`memory/embeddings.py`); `EMBED_DIM` is the single
  source of truth shared by the Pinecone index creation, upsert, and query.
- CPU-bound `encode()` is run via `asyncio.to_thread(...)` to avoid blocking the
  event loop (`memory/l3_vectors.py:embed_text`).
- Only **summaries** (and permanent-memory content) are embedded — not raw turns.

### 3.4 Categorization / tagging / per-user scoping
- **Typed entities:** every extracted entity gets an `entity_type`
  (`PROJECT, SKILL, PERSON, GOAL, TOPIC, DECISION, TASK`) and a `confidence`.
- **Topics:** free-form topic strings on each session.
- **Confidence gating:** HIGH → written to the graph immediately;
  MEDIUM/LOW → parked in `pending_confirmations` for user approval (System B).
- **Per-user scoping:** **single-tenant today** — everything hangs off one root
  node (`User`/`Person {name:"Karthik"}`) and `user_id` defaults to `"KARTHIK"`.
  See §6.3 for how to make this multi-tenant.

---

## 4. WRITE PATH (how memories are created/updated)

### 4.1 When extraction happens
- **Session end** — `memory_engine.save_session(...)` is fired (background) from
  the supervisor graph (`backend/app/core/supervisor_graph.py:204`) and from
  `SessionManager` on session finalize (`session_manager.py:711`).
- **L1 overflow** — when the in-memory window exceeds 2000 tokens, the backend
  orchestrator runs `process_overflow → summarize → MemorySaga`
  (`backend/app/services/memory_orchestrator.py:37`).

### 4.2 Extraction (System A) — `memory/entity_extractor.py`
1. Transcript is truncated (≤500 chars/turn, ≤6000 total).
2. Groq `llama-3.3-70b-versatile`, `temperature=0.1`, prompted to return JSON:
   `{ entities:[{name, entity_type, description, confidence}], summary, primary_topic }`.
3. JSON fences stripped; entities validated against `ENTITY_TYPES`; coerced into
   `Entity` dataclasses.

### 4.3 The write pipeline (System A) — `memory/memory_engine.py:save_session`
```python
extraction = await entity_extractor.extract(messages, workflow_type)   # Groq
metadata   = SessionMetadata(... summary, entities, topics ...)
await l4_store.save_session(metadata, messages)                        # L4 first (durable)
await asyncio.gather(                                                  # then fan out
    self._save_to_l3(...),   # Pinecone: embed(summary) → upsert(id=session_id)
    self._save_to_l2(...),   # Neo4j: upsert each entity, link Session-[:COVERS]->entity,
    return_exceptions=True,  #         update User.current_focus if a PROJECT was seen
)
await l1_cache.flush_session_keys(session_id)        # L1 cleanup
await prefetch_engine.refresh_known_entities()       # refresh spotting vocabulary
for e in entities: await l1_cache.invalidate_entity_context(e.name)   # bust stale cache
```
Per-layer failures are isolated (`return_exceptions=True`) so one down store never
loses the others.

### 4.4 The Saga / Outbox write (System B) — `memory/memory_saga.py:execute`
```
1. summary  = summa.TextRank(conversation, ratio=0.3)[:5 sentences][:300 chars]
2. entities = Groq llama-3.3-70b (JSON: session_properties / relationships / new_nodes)
3. Mongo.insert(... embedding_status="pending", neo4j_status="pending")   ← COMMIT POINT
   (if Mongo fails → abort whole saga)
4. Pinecone.upsert(embed(summary))  → on success flip embedding_status="complete"
5. Neo4j: create Session node + RELATED_TO Person + typed edges  → flip neo4j_status="complete"
6. MEDIUM/LOW entities → pending_confirmations
```
`SagaRetryWorker` (same file) polls every 30s for sessions still `partial_sync`
with a non-complete status and re-runs the saga (backoff 30→60→120s, dead-letter
after 3 failures). This is the **zero-data-loss guarantee**.

### 4.5 Deduplication & conflict resolution
- **Neo4j:** `MERGE` on `{name}` for every node; `ON CREATE SET … ON MATCH SET
  last_seen=…`. Uniqueness constraints back this. No duplicate entities ever.
- **Mongo `sessions`:** unique index on `session_id`; `replace_one(..., upsert=True)`.
- **Mongo `entities`:** unique `(name, entity_type)`; `replace_one(upsert)` updates
  description/confidence in place.
- **Pinecone:** `id = session_id`, so re-upsert overwrites the prior vector.
- **Content dedup:** `summary_hash = sha256(summary)` is stored to detect identical
  re-summaries.
- **Confidence-based conflict handling:** new low-confidence facts don't overwrite —
  they wait in `pending_confirmations` for explicit approval
  (`memory_orchestrator.confirm_entity`).

### 4.6 Summarization / compression
- **System A:** Groq abstractive summary (3–5 bullets).
- **System B:** `summa` **TextRank** extractive summary, top ~30% of sentences,
  capped at 5 sentences / 300 chars, with a raw-prefix fallback.
- Only the summary is embedded and recalled; raw transcript is kept solely for
  audit and expires in 90 days.

---

## 5. READ PATH (how memories are retrieved)

### 5.1 Retrieval strategy (System A) — `memory/memory_engine.py:get_context_for_session`
```
1. L1 check: retrieved_ctx:{session_id} already cached?  → return (fast path)
2. Entity spotting (no LLM): case-insensitive match of user_input against
   the set of known entity names from Neo4j (entity_extractor.spot_entities_in_text)
   + append User.current_focus
3. For each spotted entity (max 5):
     a. L1 entity_ctx:{entity} hit?  → use cached sessions
     b. else  L2: get_cluster_session_ids([entity], depth=2)     # graph neighborhood
              L3: search_by_text(user_input, top_k=3, filter_session_ids=cluster)
              L4: get_sessions_by_ids(top ids)                    # hydrate summaries
4. Fallback (no entities/results): global L3 search_by_text → L4 hydrate
5. Dedup by session_id, cap to MEMORY_TOP_K_SESSIONS (=3)
6. Cache result in L1; start session tracking; fire prefetch for spotted entities
```
This is **graph-guided semantic search**: the graph narrows the candidate set, the
vector store ranks within it, MongoDB supplies the text. Recency is folded in via
`importance_score` (`0.4*msg_count + 0.4*recency`, ×1.5 if pinned) computed at write.

### 5.2 Retrieval strategy (System B / RRF) — `memory_orchestrator.py`
Runs Neo4j graph search and Pinecone semantic search **in parallel**, then merges
ranked lists with **Reciprocal Rank Fusion**:
```
score(session) = Σ  1 / (k + rank)        with k = 60
```
Top-k fused `session_id`s are hydrated from MongoDB and rendered to XML. Hard
`asyncio.wait_for` timeout (1.5s in the voice path) returns an empty-but-valid
context rather than blocking. Circuit breakers (`circuit_l2_vector`,
`circuit_l3_graph`) trip to fallbacks when a store is unhealthy.

### 5.3 Speculative prefetch (L1.5) — `memory/prefetch_engine.py`
On **every** user message, entities are spotted and a bounded async queue
(`maxsize=50`, backpressure via `put_nowait`) fans out `L2→L3→L4` for any entity
not already cached, then writes the result to `entity_ctx:{entity}` in Redis. By
the time retrieval runs, the hot path is usually a pure Redis read.

### 5.4 Injection into the context window
Retrieved sessions are formatted and concatenated into the **system prompt**:
- System A: `memory_engine.format_context_for_prompt` →
  ```
  --- RELEVANT PAST CONTEXT ---
  [2024-01-01 | research]
  Topics: ASTA, Neo4j
  <summary>
  --- END PAST CONTEXT ---
  ```
  Injected by `other_workflow`: `system = f"{CHAT_SYSTEM}\n\n{memory_context}"`
  (`supervisor_graph.py:191`).
- System B emits **structured XML** (`<memory_context><core_identity>…
  <episodic_recall><episode>…`) — XML boundaries are used deliberately to reduce
  hallucination vs. a flat blob.

### 5.5 Token-budget management
- Only **top-3 sessions** (`MEMORY_TOP_K_SESSIONS`) injected.
- Each is a short summary (~300 chars), not a transcript.
- Vector metadata carries only a 200-char `summary_snippet`.
- Extraction input capped at 6000 chars; per-turn 500 chars.
- L1 live window capped at 2000 tokens (rough `len/4` estimate).
- Hard retrieval timeouts (`RETRIEVAL_TIMEOUT_SECONDS=2.0`; 1.5s voice; saga read
  budgets) bound worst-case cost.

---

## 6. PERSISTENCE & STATE

### 6.1 Across sessions / logins
- **Durable:** MongoDB (sessions, summaries, permanent memory, entities), Pinecone
  (vectors), Neo4j (graph). These survive restarts and define "memory."
- **Ephemeral:** Redis (TTL'd) and the in-process deque — pure acceleration, safe
  to lose.
- **Connections** are module-level singletons created once and pooled
  (`AsyncIOMotorClient(maxPoolSize=50,…)`, Neo4j driver `max_connection_pool_size=50`,
  one Pinecone index handle) to avoid per-request reconnect latency.

### 6.2 Conversation thread state
LangGraph is compiled with a **checkpointer** keyed by `thread_id = session_id`
(`supervisor_graph.py:get_supervisor_graph`). Backend: Postgres
(`langgraph-checkpoint-postgres`) or MongoDB (`langgraph-checkpoint-mongodb`),
falling back to in-memory `MemorySaver`. This persists mid-conversation
**interrupts** (clarifying questions) so a turn can resume via `Command(resume=…)`.

### 6.3 User identification & multi-tenancy (currently single-tenant)
Today the system is hardwired to one user: a single root node
`User/Person {name:"Karthik"}`, `user_id` defaulting to `"KARTHIK"`, and global
Redis keys. To generalize for the rebuild:
- **Mongo:** add `user_id` to every doc and to every filter; compound indexes
  `(user_id, session_id)`.
- **Pinecone:** use **one namespace per user** (or a `user_id` metadata filter).
- **Neo4j:** one root `User {id}` per tenant; scope all `MATCH`/`MERGE` through it.
- **Redis:** prefix every key with `{user_id}:` (e.g. `u123:entity_ctx:ASTA`).
- **Auth:** today a static JWT/token (`ASTA_JWT_TOKEN`) identifies the single user
  (`backend/app/auth/middleware.py`); replace with real per-user auth → `user_id`.

### 6.4 Lifecycle (`backend/app/main.py`)
- **startup:** preload MiniLM; `saga_retry_worker.start()`;
  `memory_engine.connect_all()` (connects L1–L4 + starts prefetch).
- **shutdown:** `memory_engine.disconnect_all()`; drain + stop retry worker; close
  checkpointer; shut down task registry.

---

## 7. KEY FILES & FUNCTIONS

### Canonical layer (`memory/`)
| File | Class / fn | One-liner |
|------|-----------|-----------|
| `memory/__init__.py` | exports `memory_engine` | the only intended public import |
| `memory/memory_engine.py` | `MemoryEngine` | master orchestrator: connect_all, get_context_for_session, save_session, remember/recall, format_context_for_prompt |
| `memory/schema.py` | `Entity`, `SessionMetadata`, `NEO4J_LABELS/RELATIONSHIPS`, `ENTITY_TYPES` | single source of truth for data shapes |
| `memory/l1_cache.py` | `L1Cache` | Redis hot cache: active sessions, entity_ctx, retrieved_ctx (TTLs) |
| `memory/l1_session.py` | `L1Session`, `L1SessionManager` | in-RAM 2000-token sliding window; signals overflow |
| `memory/prefetch_engine.py` | `PrefetchEngine` | L1.5 speculative background entity loading (bounded queue) |
| `memory/l2_graph.py` | `L2Graph` | Neo4j: upsert_entity, link_session_to_entities, **get_cluster_session_ids** (core 2-hop query), current_focus |
| `memory/l3_vectors.py` | `L3Vectors` | Pinecone: embed_text, upsert_session, **search_by_text** (with session_id filter) |
| `memory/l4_store.py` | `L4Store` | MongoDB: save_session, get_sessions_by_ids, permanent memory, entities, indexes/TTL |
| `memory/embeddings.py` | `embed()`, `EmbeddingService`, `EMBED_DIM` | MiniLM 384-d, loaded once |
| `memory/entity_extractor.py` | `EntityExtractor` | Groq JSON entity+summary extraction; `spot_entities_in_text` (no-LLM matcher) |

### Saga / orchestrator variant (`memory/`)
| File | Class / fn | One-liner |
|------|-----------|-----------|
| `memory/memory_saga.py` | `MemorySaga`, `SagaRetryWorker`, `SessionData` | Outbox 3-phase write Mongo→Pinecone→Neo4j + retry worker |
| `memory/memory_orchestrator.py` | `MemoryOrchestrator` | RRF-fusion read (graph∥vector), persistent conns, commit_session, confirm_entity |
| `memory/graph_service.py` | `GraphService` | Neo4j identity tree (Person→Category→…), create_session_node, typed edges, search_graph_context |
| `memory/schema_init.py` | `initialize_schema()` | idempotent (MERGE) seed of the graph; run once |

### Backend integration
| File | Where it matters |
|------|------------------|
| `backend/app/config.py` | all tunables (`Settings`) — TTLs, top-k, depth, dims, URIs |
| `backend/app/core/supervisor_graph.py` | injects memory on turn start (`run_supervisor_graph`), fires `save_session` node on turn end |
| `backend/app/services/session_manager.py` | builds summary/embedding/importance, runs MemorySaga + `memory_engine.save_session` on session end |
| `backend/app/services/memory_orchestrator.py` | `process_overflow` (L1→saga), `cross_tier_retrieve` (delegates to `memory_engine`, legacy RRF fallback + circuit breakers) |
| `backend/app/services/preferences_service.py` | typed user preferences (semantic memory), NL→JSON updates |
| `backend/app/api/ws_routes.py` | live wiring: `l1_manager`, prefetch trigger, RAG injection |

### Core data flow: "user sends message" → "memory updated"
```
1. WS/HTTP receives message  (ws_routes.py / run_supervisor_graph)
2. READ: memory_engine.get_context_for_session(session_id, text, wf)
      L1 retrieved_ctx? → else spot entities → L2 cluster → L3 vector(filter) → L4 hydrate
      → format_context_for_prompt → injected into system prompt
   (in parallel) prefetch_engine.on_message(...) warms L1 entity_ctx for next turn
3. LLM generates response (supervisor graph: classify_intent → workflow → response)
4. WRITE (background, non-blocking) on turn/session end:
      entity_extractor.extract (Groq) → SessionMetadata
      L4 save full session  →  ∥ L3 upsert(summary vector) + L2 upsert entities & links
      → L1 flush + prefetch.refresh + invalidate entity caches
   (System B path: L1 overflow OR session end → MemorySaga Outbox write + retry worker)
5. Long-term stores now reflect the turn; next session's READ can recall it.
```

---

## 8. TECH STACK & DEPENDENCIES

**Language / runtime:** Python 3.11+, fully `asyncio`.

**Framework:** FastAPI + Uvicorn (`@app.on_event` lifespan). Orchestration via
**LangGraph** (`StateGraph`, checkpointers) and **LangChain** (`langchain`,
`langchain-community`).

**Datastores & clients**
- MongoDB — `motor` (async) + `pymongo` (IndexModel/TTL)
- Pinecone — `pinecone` (serverless, cosine, 384-d)
- Neo4j — `neo4j` async driver (Aura)
- Redis — `redis==5.1.0` + `hiredis==3.0.0` (`redis.asyncio`)

**ML / NLP**
- Embeddings — `sentence-transformers` (`all-MiniLM-L6-v2`, 384-d), `torch`, `transformers`
- Summarization — `summa` (TextRank, System B) and Groq abstractive (System A)
- LLM extraction — **Groq** `llama-3.3-70b-versatile` via `groq` SDK and `langchain-groq`

**External services:** Groq (LLM), Pinecone (managed vectors), Neo4j Aura (managed
graph), MongoDB Atlas, Redis. (Adjacent, not core memory: Deepgram STT/TTS, Notion,
Google Calendar, Serper, Gemini/OpenAI/Anthropic.)

**Config (`pydantic-settings`, `.env`)** — key knobs:
```
REDIS_URL, REDIS_TTL_HOT=3600, REDIS_TTL_PREFETCH=1800, REDIS_TTL_ENTITY=86400
MEMORY_TOP_K_SESSIONS=3, MEMORY_CLUSTER_DEPTH=2, MEMORY_PREFETCH_ENABLED=true
SESSION_TRANSCRIPT_TTL_DAYS=90, PINECONE_EMBEDDING_DIM=384
EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"
PINECONE_INDEX_NAME="asta-memory", DB_NAME="asta_db"
MONGO_URI, PINECONE_API_KEY, NEO4J_URI/USERNAME/PASSWORD, GROQ_API_KEY
RETRIEVAL_TIMEOUT_SECONDS=2.0
```

---

## 9. REBUILD CHECKLIST (minimum viable port)

1. **Pick the layers you need.** Minimum useful set = L3 (vectors) + L4 (Mongo).
   Add L2 (graph) for relationship recall; add L1 (Redis) + L1.5 (prefetch) only
   if you need voice-grade latency.
2. **Embeddings:** load MiniLM once; centralize `EMBED_DIM`; size the vector index
   to it; run `encode` off-thread.
3. **Write pipeline:** on session end → extract (LLM JSON) → save full doc →
   embed+upsert summary → upsert graph entities + session links. Use the
   **Outbox/Saga + retry worker** from System B for durability.
4. **Read pipeline:** entity-spot → graph cluster → vector search filtered by
   cluster ids → hydrate from doc store → **RRF fuse** graph+vector → inject top-k
   summaries as XML into the system prompt. Wrap in a hard timeout.
5. **Dedup:** `MERGE` graph nodes; unique indexes + upsert in Mongo; `id=session_id`
   in the vector store; `summary_hash` for content dedup.
6. **Make it multi-tenant from day one** (see §6.3) — retrofitting `user_id` later
   is painful.
7. **Unify the schema** — do **not** copy both naming schemes (`User`/`Person`,
   `asta_db`/`asta_memory`); pick one.
