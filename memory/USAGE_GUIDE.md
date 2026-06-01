# ASTA Memory System - Usage Guide

## Quick Start

```python
from memory import memory_engine

# 1. Connect all layers (do this once at app startup)
await memory_engine.connect_all()

# 2. Get context at session start
context = await memory_engine.get_context_for_session(
    session_id="session-123",
    user_input="Let's work on the ASTA project",
    workflow_type="research"
)

# 3. Format context for LLM prompt
formatted = memory_engine.format_context_for_prompt(context)
# Inject this into your system prompt

# 4. Track entities during conversation
await memory_engine.on_user_message(
    session_id="session-123",
    message="I decided to use Redis for caching"
)

# 5. Save session at the end
await memory_engine.save_session(
    session_id="session-123",
    workflow_type="research",
    messages=[
        {"role": "user", "content": "Let's work on ASTA"},
        {"role": "assistant", "content": "Sure! What part?"},
        # ... more messages
    ],
    start_time="2026-04-21T10:00:00",
    notion_page_id="optional-notion-page-id"
)

# 6. Permanent memory (optional)
doc = await memory_engine.remember(
    "Karthik prefers Redis for L1 cache",
    tags=["preference", "architecture", "Redis"]
)

# 7. Recall permanent memories
memories = await memory_engine.recall("Redis preference")
```

## API Reference

### `connect_all() -> Dict[str, str]`
Connect all memory layers. Call once at app startup.

**Returns:**
```python
{
    "L1_redis": "connected",
    "L2_neo4j": "connected",
    "L3_pinecone": "connected",
    "L4_mongodb": "connected",
    "prefetch_engine": "started"
}
```

### `get_context_for_session(session_id, user_input, workflow_type) -> Dict`
Retrieve relevant past context for a new session.

**Args:**
- `session_id` (str): Unique session identifier
- `user_input` (str): User's first message
- `workflow_type` (str): "research", "routine", or "content"

**Returns:**
```python
{
    "sessions": [
        {
            "session_id": "...",
            "workflow_type": "research",
            "summary": "...",
            "entities": [...],
            "topics": [...],
            "end_time": "2026-04-21T10:00:00"
        }
    ],
    "from_cache": False,
    "entities_spotted": ["ASTA", "Redis"]
}
```

### `format_context_for_prompt(context_result) -> str`
Format retrieved context for LLM prompt injection.

**Args:**
- `context_result` (Dict): Result from `get_context_for_session()`

**Returns:**
```
--- RELEVANT PAST CONTEXT ---

[2026-04-21 | research]
Topics: ASTA, Redis, Neo4j
The conversation was about implementing the memory layer...

--- END PAST CONTEXT ---
```

### `on_user_message(session_id, message) -> None`
Track entities mentioned in user messages. Non-blocking, triggers prefetch.

**Args:**
- `session_id` (str): Current session ID
- `message` (str): User's message

### `save_session(session_id, workflow_type, messages, start_time, notion_page_id="") -> bool`
Save complete session at the end. Extracts entities, generates summary, saves to all layers.

**Args:**
- `session_id` (str): Unique session identifier
- `workflow_type` (str): "research", "routine", or "content"
- `messages` (List[Dict]): Conversation messages
- `start_time` (str): ISO datetime when session started
- `notion_page_id` (str, optional): Notion page ID if created

**Returns:** `True` on success, `False` on failure

### `remember(content, tags) -> Dict`
Save to permanent memory (things user explicitly wants remembered).

**Args:**
- `content` (str): What to remember
- `tags` (List[str]): Tags for categorization

**Returns:**
```python
{
    "memory_id": "uuid",
    "content": "...",
    "tags": ["tag1", "tag2"],
    "date_stored": "2026-04-21T10:00:00",
    "recalled_count": 0
}
```

### `recall(query_text, top_k=5) -> List[Dict]`
Recall permanent memories by semantic search.

**Args:**
- `query_text` (str): What to search for
- `top_k` (int): Number of results

**Returns:** List of memory documents

### `health_check() -> Dict`
Check health of all memory layers.

**Returns:**
```python
{
    "l1_redis": True,
    "l2_neo4j": True,
    "l3_pinecone": True,
    "l4_mongodb": True,
    "prefetch_queue_size": 0
}
```

## Entity Types

The system extracts 7 types of entities:

1. **PROJECT** - Specific projects (e.g., "ASTA", "portfolio website")
2. **SKILL** - Technical/personal skills (e.g., "Python", "LangGraph")
3. **PERSON** - People mentioned (e.g., "Ravi", "my CTO")
4. **GOAL** - Goals/aspirations (e.g., "grow community to 1000")
5. **TOPIC** - Knowledge topics (e.g., "transformer architecture")
6. **DECISION** - Decisions made (e.g., "use Redis for caching")
7. **TASK** - Action items (e.g., "call Ravi tomorrow")

## Integration with LangGraph

```python
from langgraph.graph import StateGraph
from memory import memory_engine

class ASTAState(TypedDict):
    session_id: str
    workflow_type: str
    messages: List[Dict]
    memory_context: str  # Injected from memory system

async def start_session_node(state: ASTAState):
    """First node in your graph - load memory context"""
    context = await memory_engine.get_context_for_session(
        session_id=state["session_id"],
        user_input=state["messages"][-1]["content"],
        workflow_type=state["workflow_type"]
    )
    
    formatted = memory_engine.format_context_for_prompt(context)
    
    return {
        **state,
        "memory_context": formatted
    }

async def llm_node(state: ASTAState):
    """Your LLM node - use memory context in system prompt"""
    system_prompt = f"""You are ASTA, Karthik's personal AI assistant.
    
{state["memory_context"]}

Now respond to the user's message..."""
    
    # Call your LLM with the system prompt
    # ...

async def end_session_node(state: ASTAState):
    """Last node - save session to memory"""
    await memory_engine.save_session(
        session_id=state["session_id"],
        workflow_type=state["workflow_type"],
        messages=state["messages"],
        start_time=state.get("start_time", ""),
        notion_page_id=state.get("notion_page_id", "")
    )
    
    return state
```

## Configuration

All configuration is in `.env`:

```bash
# Memory Layer
REDIS_URL=redis://localhost:6379/0
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
PINECONE_API_KEY=your-key
PINECONE_INDEX_NAME=asta-memory-v2
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/

# LLM & Embeddings
GROQ_API_KEY=your-key  # For entity extraction
GEMINI_API_KEY=your-key  # For embeddings

# Memory Settings
MEMORY_TOP_K_SESSIONS=3  # How many past sessions to inject
MEMORY_CLUSTER_DEPTH=2  # Neo4j traversal depth
SESSION_TRANSCRIPT_TTL_DAYS=90  # Delete raw transcripts after 90 days
```

## Performance Tips

1. **Cache Hits**: The system caches retrieved context in Redis. Subsequent calls in the same session are instant.

2. **Prefetch**: Call `on_user_message()` on every user message to trigger background prefetch of entity context.

3. **Batch Sessions**: If saving multiple sessions, do them in parallel:
   ```python
   await asyncio.gather(
       memory_engine.save_session(...),
       memory_engine.save_session(...),
       memory_engine.save_session(...)
   )
   ```

4. **Health Checks**: Run `health_check()` periodically to monitor layer health.

## Troubleshooting

### "Failed to connect to Pinecone"
- Check `PINECONE_API_KEY` in `.env`
- Verify index name matches: `asta-memory-v2`

### "Failed to embed text"
- Check `GEMINI_API_KEY` in `.env`
- Ensure text is not empty

### "Empty embedding for session"
- Summary might be empty - check entity extraction logs
- Verify Groq API key is valid

### "Sessions retrieved: 0"
- Pinecone indexing takes ~2 seconds
- Wait a bit after saving before querying
- Check if vectors were actually upserted (logs)

### "Cannot do exclusion on field"
- MongoDB projection error - already fixed in latest code
- Update to latest `memory/l4_store.py`

## Testing

Run the test suite:
```bash
python memory/test_memory.py
```

Expected output:
```
=== ASTA Memory Layer E2E Test ===

1. Connecting all layers...
   Status: {'L1_redis': 'connected', ...}

2. Simulating Session 1 (ASTA project)...
   Session 1 saved: True

3. Simulating Session 2 (retrieving context about ASTA)...
   Sessions retrieved: 1
   Entities spotted: ['ASTA', 'memory layer']
   
4. Testing permanent memory...
   Saved permanent memory: <uuid>
   Recalled: 0 memories

5. Health check...
   {'l1_redis': True, 'l2_neo4j': True, ...}

=== Test Complete ===
```
