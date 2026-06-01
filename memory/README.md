# ASTA Memory Layer

Complete 3-layer memory system for ASTA personal AI.

## Architecture

### L1 - Active Session (In-Memory)
- **File**: `l1_session.py`
- Sliding window deque with 2000 token limit
- Lives in RAM, dies when session ends
- Triggers overflow to L2 when limit exceeded

### L2 - Episodic Memory (MongoDB + Pinecone)
- **MongoDB**: Compressed session summaries
- **Pinecone**: 384-dim vector embeddings
- Used for semantic search across past conversations

### L3 - Knowledge Graph (Neo4j)
- **File**: `graph_service.py`
- Identity layer defining who Karthik is
- Dynamic graph with entity extraction
- Graph-guided vector search

## Files

1. **`l1_session.py`** - In-memory session manager with token tracking
2. **`embeddings.py`** - Sentence-transformers embedding service (384-dim)
3. **`memory_saga.py`** - Atomic write pipeline (MongoDB → Pinecone → Neo4j)
4. **`saga_retry_worker.py`** - Background retry worker with exponential backoff
5. **`memory_orchestrator.py`** - Read flow with RRF fusion and 1.5s timeout
6. **`graph_service.py`** - Neo4j service with exact ASTA schema
7. **`schema_init.py`** - Idempotent schema initialization script

## Schema

### Neo4j Structure

```
Person (Karthik)
├── HAS_CATEGORY → Skills
│   ├── CONTAINS → SkillGroup (Programming Languages)
│   │   └── CONTAINS → Skill (Python)
│   ├── CONTAINS → SkillGroup (Frameworks)
│   │   └── CONTAINS → Skill (FastAPI)
│   ├── CONTAINS → SkillGroup (Databases)
│   │   ├── CONTAINS → Skill (MongoDB)
│   │   ├── CONTAINS → Skill (Neo4j)
│   │   └── CONTAINS → Skill (Pinecone)
│   ├── CONTAINS → SkillGroup (AI & ML)
│   │   └── CONTAINS → Skill (Groq)
│   └── CONTAINS → SkillGroup (Dev Tools)
├── HAS_CATEGORY → Projects
│   └── CONTAINS → Project (ASTA)
├── HAS_CATEGORY → Tools
│   ├── CONTAINS → Tool (Notion)
│   ├── CONTAINS → Tool (Google Calendar)
│   ├── CONTAINS → Tool (Serper Search)
│   ├── CONTAINS → Tool (Weather)
│   └── CONTAINS → Tool (Gemini)
├── HAS_CATEGORY → Interests
├── HAS_CATEGORY → People
└── HAS_CATEGORY → Commitments

Session
├── RELATED_TO → Person (always)
├── TOUCHES_PROJECT → Project
├── USES_SKILL → Skill
├── INVOLVES_TOOL → Tool
├── INVOLVES_PERSON → PersonNode
└── CREATES_COMMITMENT → Commitment
```

### Session Properties

```python
{
    "session_id": str,
    "timestamp": datetime,
    "ended_at": datetime,
    "duration_seconds": int,
    "summary": str,
    "topics": List[str],
    "tool_calls": List[str],
    "message_count": int,
    "pending_confirmations": List[Dict]
}
```

## Usage

### Initialize Schema (Run Once)

```bash
python -m memory.schema_init
```

### Write Flow (Session End)

```python
from memory import memory_orchestrator, SessionData

# Commit session to L2/L3
await memory_orchestrator.commit_session(
    session_id="session_123",
    user_id="karthik",
    timestamp="2024-01-01T00:00:00Z",
    ended_at="2024-01-01T00:30:00Z",
    duration_seconds=1800,
    raw_messages=[...],
    message_count=10,
    tool_calls=["Notion", "Serper Search"]
)
```

### Read Flow (Query)

```python
from memory import memory_orchestrator

# Retrieve relevant memory (1.5s timeout)
context_xml = await memory_orchestrator.retrieve_memory(
    query="What did we discuss about ASTA memory layer?",
    current_session_id="session_123",
    top_k=8
)
```

### Start Retry Worker (On App Boot)

```python
from memory import saga_retry_worker

# Start background retry worker
await saga_retry_worker.start()

# Stop on shutdown
await saga_retry_worker.stop()
```

## Entity Extraction

The system uses Groq `llama-3.3-70b-versatile` to extract entities from conversations:

### Confidence Levels

- **HIGH**: Create node/edge immediately
- **MEDIUM/LOW**: Store in `pending_confirmations` for Karthik's approval

### Entity Types

- **Projects**: New projects mentioned
- **Skills**: New skills/technologies discussed
- **Tools**: Tools used in session
- **People**: People mentioned
- **Interests**: New interests discovered
- **Commitments**: Promises/tasks created

## Retry Logic

### SagaRetryWorker

- Polls every 30 seconds
- Finds sessions with `embedding_status: "pending"` or `neo4j_status: "pending"`
- Exponential backoff: 30s → 60s → 120s
- Dead letter after 3 failures with critical alert

## Environment Variables

```bash
# MongoDB
MONGODB_URI=mongodb+srv://...

# Pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=asta-memory

# Neo4j
NEO4J_URI=neo4j+s://...
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...

# Groq
GROQ_API_KEY=...
```

## Critical Rules

1. **All Neo4j writes use MERGE not CREATE** - never create duplicate nodes
2. **All async functions properly awaited** - never fire-and-forget
3. **Every database operation has try/except** with specific error logging
4. **1.5s timeout is a hard `asyncio.wait_for`** - not a suggestion
5. **Pinecone search filters by session_ids** when Neo4j returns them
6. **Entity extraction returns JSON only** - strip markdown before parsing
7. **Session node creation is CRITICAL** - must succeed or abort saga

## Testing

```bash
# Test schema initialization
python -m memory.schema_init

# Test memory saga (create test script)
python test_memory_layer.py
```

## Integration with ASTA

The memory layer integrates with ASTA's WebSocket routes:

1. **On message**: Add to L1 session
2. **On overflow**: Trigger L2/L3 write via MemorySaga
3. **On query**: Retrieve context via MemoryOrchestrator
4. **On session end**: Commit full session to L2/L3

## Monitoring

- Check MongoDB `sessions` collection for `embedding_status` and `neo4j_status`
- Monitor `pending_confirmations` collection for entities awaiting approval
- Watch logs for `DEAD LETTER` alerts (critical failures)
- Query Neo4j to verify graph structure

## Next Steps

1. Run `python -m memory.schema_init` to initialize Neo4j
2. Integrate with existing ASTA WebSocket routes
3. Start `saga_retry_worker` on app boot
4. Test with real conversations
5. Monitor and tune RRF fusion parameters
