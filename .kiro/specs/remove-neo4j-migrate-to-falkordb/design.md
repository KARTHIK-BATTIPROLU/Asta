# Design Document: Remove Neo4j and Migrate to FalkorDB/Graphiti

## Overview

This design specifies the complete migration of ASTA's L2 knowledge graph layer from Neo4j Aura to FalkorDB with Graphiti. The migration will:

1. Remove all Neo4j code, dependencies, and configuration
2. Implement a new `graph_ltm.py` module using FalkorDB/Graphiti
3. Update all integration points (memory engine, prefetch engine, database manager, health checks)
4. Maintain API compatibility to minimize disruption to calling code

**Architecture Decision:** FalkorDB was chosen over Neo4j because:
- Redis-based deployment is simpler (single Redis instance vs separate Neo4j Aura)
- Graphiti provides LLM-powered entity extraction and relationship management
- Lower operational complexity and cost
- Better integration with existing Redis infrastructure

**Known Limitation:** Graphiti's `add_episode` method uses Gemini API for LLM extraction, which is rate-limited on free tier (503 errors). The workaround is manual entity creation via `upsert_entity`. Search and graph operations work normally.

## Architecture

### Current State (Neo4j)

```
Memory Engine
    ↓
memory/l2_graph.py (L2Graph class)
    ↓
Neo4j Aura (cloud-hosted)
```

**Files to Remove:**
- `memory/l2_graph.py` (318 lines, L2Graph class)
- `memory/schema_init.py` (Neo4j schema initialization)
- `initialize_graph.py` (setup script)

### Target State (FalkorDB/Graphiti)

```
Memory Engine
    ↓
backend/app/services/memory/graph_ltm.py (GraphLTM class)
    ↓
Graphiti Client
    ↓
FalkorDB (Redis module, localhost:6379)
```

**New File:**
- `backend/app/services/memory/graph_ltm.py` (new implementation)

### Integration Points

The following modules interact with the L2 layer and must be updated:

1. **memory/memory_engine.py** - Calls L2 for entity operations and cluster retrieval
2. **memory/prefetch_engine.py** - Loads known entities and performs cluster searches
3. **backend/app/db/database.py** - Manages Neo4j driver (to be removed)
4. **backend/app/api/health.py** - Health check endpoints
5. **backend/app/config.py** - Configuration parameters
6. **.env.template** - Environment variable template

## Components and Interfaces

### GraphLTM Class (New)

**File:** `backend/app/services/memory/graph_ltm.py`

**Purpose:** Unified L2 knowledge graph interface using FalkorDB/Graphiti.

**Class Structure:**

```python
class GraphLTM:
    """L2 knowledge graph layer using FalkorDB with Graphiti."""
    
    def __init__(self):
        self.graphiti: Optional[Graphiti] = None
        self.is_initialized: bool = False
        self._known_entities: List[str] = []
        self._current_focus: str = ""
    
    async def initialize(self) -> None:
        """Initialize Graphiti client and connect to FalkorDB."""
    
    async def health_check(self) -> bool:
        """Verify FalkorDB connectivity."""
    
    async def get_all_entity_names(self) -> List[str]:
        """Get all entity names for real-time entity spotting."""
    
    async def get_current_focus(self) -> Dict:
        """Get current focus entity and metadata."""
    
    async def get_cluster_session_ids(
        self, entity_names: List[str], depth: int = 2
    ) -> List[str]:
        """Find sessions connected to entities within depth hops."""
    
    async def upsert_entity(
        self, name: str, entity_type: str, 
        description: str = "", relation: str = "HAS"
    ) -> None:
        """Create or update an entity node."""
    
    async def link_session_to_entities(
        self, session_id: str, entities: List,
        workflow_type: str, summary_snippet: str
    ) -> None:
        """Link a session to all discussed entities."""
    
    async def update_current_focus(self, entity_name: str) -> None:
        """Update current work focus."""
    
    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search entities using Graphiti."""
    
    async def add_episode(
        self, content: str, session_id: str
    ) -> None:
        """Add episode to graph (LLM extraction - rate limited)."""
    
    async def disconnect(self) -> None:
        """Graceful shutdown."""
```

**Method Behaviors:**

1. **initialize()**: 
   - Create Graphiti client with FalkorDB connection
   - Use settings.FALKORDB_HOST, FALKORDB_PORT, FALKORDB_DATABASE
   - Set is_initialized = True on success
   - Log connection status

2. **get_all_entity_names()**:
   - Query Graphiti for all entity nodes
   - Return list of entity names
   - Cache in self._known_entities for fast spotting

3. **get_current_focus()**:
   - Return dict with current_focus, last_active_project, last_active
   - Store focus in instance variable or Redis cache

4. **get_cluster_session_ids(entity_names, depth)**:
   - Use Graphiti search to find entities matching entity_names
   - Traverse relationships up to depth hops
   - Return session IDs connected to found entities
   - Limit to 50 sessions max

5. **upsert_entity(name, type, description, relation)**:
   - Create entity node in FalkorDB with Graphiti
   - Store entity_type, description, relation metadata
   - Update _known_entities cache

6. **link_session_to_entities(session_id, entities, workflow_type, summary)**:
   - Create session node with metadata
   - Create edges from session to each entity
   - Use COVERS relationship type

7. **update_current_focus(entity_name)**:
   - Store entity_name as current focus
   - Update last_active timestamp

8. **health_check()**:
   - Attempt simple query to FalkorDB
   - Return True if connected, False otherwise

9. **search(query, limit)**:
   - Use Graphiti search API
   - Return top-k matching entities

10. **add_episode(content, session_id)**:
    - Attempt Graphiti add_episode with LLM extraction
    - Catch rate limit errors and log gracefully
    - Document that this is currently disabled

**Singleton Pattern:**

```python
graph_ltm = GraphLTM()
```

Export singleton instance for import by memory engine and prefetch engine.

### Configuration Updates

**backend/app/config.py:**

Add FalkorDB parameters:
```python
class Settings(BaseSettings):
    # FalkorDB Configuration
    FALKORDB_HOST: str = "localhost"
    FALKORDB_PORT: int = 6379
    FALKORDB_USERNAME: str = ""
    FALKORDB_PASSWORD: str = ""
    FALKORDB_DATABASE: str = "asta_graph"
```

Remove Neo4j parameters:
```python
# DELETE THESE:
NEO4J_URI: str = ""
NEO4J_USERNAME: str = "neo4j"
NEO4J_PASSWORD: str = ""
NEO4J_DATABASE: str = "neo4j"
```

**.env.template:**

Add:
```bash
# FalkorDB Configuration (Redis-based graph database)
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_USERNAME=
FALKORDB_PASSWORD=
FALKORDB_DATABASE=asta_graph
```

Remove:
```bash
# DELETE THESE:
NEO4J_URI=...
NEO4J_USERNAME=...
NEO4J_PASSWORD=...
NEO4J_DATABASE=...
AURA_INSTANCEID=...
AURA_INSTANCENAME=...
```

### Memory Engine Updates

**File:** `memory/memory_engine.py`

**Changes:**

1. **Import Update:**
```python
# OLD:
from memory.l2_graph import l2_graph

# NEW:
from backend.app.services.memory.graph_ltm import graph_ltm
```

2. **Variable Rename:**
Replace all occurrences of `l2_graph` with `graph_ltm`.

3. **connect_all() Method:**
```python
async def connect_all(self) -> Dict[str, str]:
    layers = [
        ("L1_redis", l1_cache),
        ("L2_graphiti", graph_ltm),  # Changed from L2_neo4j
        ("L3_pinecone", l3_vectors),
        ("L4_mongodb", l4_store),
    ]
    
    for name, layer in layers:
        try:
            if name == "L2_graphiti":
                await layer.initialize()  # Graphiti uses initialize() not connect()
            else:
                await layer.connect()
            results[name] = "connected"
```

4. **Method Calls:**
All method calls remain the same (API compatibility), just directed to graph_ltm:
- `graph_ltm.get_all_entity_names()`
- `graph_ltm.get_current_focus()`
- `graph_ltm.get_cluster_session_ids(entity_names, depth)`
- `graph_ltm.upsert_entity(name, type, description, relation)`
- `graph_ltm.link_session_to_entities(...)`
- `graph_ltm.update_current_focus(entity_name)`

### Prefetch Engine Updates

**File:** `memory/prefetch_engine.py`

**Changes:**

1. **Import Update:**
```python
# In _import_dependencies():
from backend.app.services.memory.graph_ltm import graph_ltm
self._l2_graph = graph_ltm
```

2. **Method Calls:**
Replace `self._l2_graph` calls with `graph_ltm` calls (already using the variable):
- `await self._l2_graph.get_all_entity_names()`
- `await self._l2_graph.get_cluster_session_ids(entity_names, depth)`

No other changes needed since the prefetch engine already uses dynamic imports.

### Database Manager Updates

**File:** `backend/app/db/database.py`

**Changes:**

1. **Remove Neo4j Import:**
```python
# DELETE:
from neo4j import AsyncGraphDatabase
```

2. **Remove Neo4j Driver:**
```python
# DELETE from __new__():
cls._instance.neo4j_driver = None
```

3. **Remove Neo4j Connection in connect():**
```python
# DELETE entire section:
# 2. Neo4j Aura Connection
try:
    neo4j_uri = ...
    self.neo4j_driver = AsyncGraphDatabase.driver(...)
    logger.info("[DatabaseManager] Neo4j Aura Graph Database bindings initialized.")
except Exception as e:
    logger.critical(f"[DatabaseManager] Failed to connect to Neo4j: {e}")
    raise e
```

4. **Remove Neo4j from ping():**
```python
# DELETE:
# Ping Neo4j
if self.neo4j_driver:
    try:
        await self.neo4j_driver.verify_connectivity()
        logger.info("✔️  Neo4j Aura Health Check: Passed")
    except Exception as e:
        logger.error(f"❌ Neo4j Authentication Error or Instance Unavailable: {e}")
        health = False
```

5. **Remove Neo4j from disconnect():**
```python
# DELETE:
if self.neo4j_driver:
    await self.neo4j_driver.close()
    logger.info("[DatabaseManager] Neo4j bindings shutdown.")
```

**Note:** FalkorDB initialization is handled by graph_ltm, not database manager, since it uses Graphiti client which manages the connection internally.

### Health Check Updates

**File:** `backend/app/api/health.py`

**Changes:**

1. **Remove Neo4j Health Check from deep_health_check():**
```python
# DELETE:
# Check Neo4j
try:
    from memory.l2_graph import graph_store
    result = await graph_store.query("RETURN 1 as test")
    health_status["services"]["neo4j"] = {
        "status": "ok",
        "message": "Connected"
    }
except Exception as e:
    health_status["services"]["neo4j"] = {
        "status": "error",
        "message": str(e)
    }
    health_status["overall"] = "degraded"
```

2. **Add FalkorDB Health Check:**
```python
# Check FalkorDB
try:
    from backend.app.services.memory.graph_ltm import graph_ltm
    if graph_ltm.is_initialized:
        is_healthy = await graph_ltm.health_check()
        health_status["services"]["falkordb"] = {
            "status": "ok" if is_healthy else "error",
            "message": "Connected" if is_healthy else "Connection failed"
        }
    else:
        health_status["services"]["falkordb"] = {
            "status": "not_initialized",
            "message": "GraphLTM not initialized"
        }
except Exception as e:
    health_status["services"]["falkordb"] = {
        "status": "error",
        "message": str(e)
    }
    health_status["overall"] = "degraded"
```

## Data Models

### Entity Node (FalkorDB)

Stored in FalkorDB via Graphiti:

```python
{
    "name": str,              # Entity name (e.g., "ASTA", "Python", "Karthik")
    "entity_type": str,       # Type: PROJECT, SKILL, PERSON, TOPIC, TOOL, COMMITMENT
    "description": str,       # Optional description
    "relation_to_user": str,  # Relationship type (e.g., "WORKING_ON", "HAS", "KNOWS")
    "created_at": datetime,   # Creation timestamp
    "last_seen": datetime     # Last mentioned timestamp
}
```

### Session Node (FalkorDB)

```python
{
    "session_id": str,        # Unique session identifier
    "workflow_type": str,     # research, routine, general, etc.
    "summary": str,           # First 200 chars of summary
    "created_at": datetime    # Session timestamp
}
```

### Relationships (FalkorDB)

**User → Entity:**
- Type: Varies (WORKING_ON, HAS, KNOWS, etc.)
- Connects root "Karthik" user node to entities

**Session → Entity:**
- Type: COVERS
- Connects session nodes to discussed entities

**Entity → Entity:**
- Type: RELATED_TO
- Connects related entities (e.g., Python → FastAPI)

### Graphiti Search Results

```python
[
    {
        "entity_name": str,
        "entity_type": str,
        "description": str,
        "relevance_score": float
    },
    ...
]
```

### Cluster Retrieval Results

```python
List[str]  # List of session_id strings, max 50
```

## Error Handling

### Connection Failures

**Scenario:** FalkorDB not running or not configured

**Handling:**
1. `initialize()` catches connection errors
2. Sets `is_initialized = False`
3. Logs error with clear message
4. Returns gracefully without crashing app
5. Health checks report "not_configured" or "error" status

**Example:**
```python
async def initialize(self) -> None:
    try:
        self.graphiti = Graphiti(
            host=settings.FALKORDB_HOST,
            port=settings.FALKORDB_PORT,
            database=settings.FALKORDB_DATABASE
        )
        self.is_initialized = True
        logger.info("GraphLTM initialized with FalkorDB")
    except Exception as e:
        self.is_initialized = False
        logger.error(f"Failed to initialize GraphLTM: {e}")
        logger.warning("L2 layer will be non-functional until FalkorDB is configured")
```

### Graphiti Rate Limiting

**Scenario:** `add_episode` hits Gemini API rate limits (503 errors)

**Handling:**
1. Catch specific rate limit exceptions
2. Log warning with explanation of limitation
3. Fall back to manual entity creation via `upsert_entity`
4. Document workaround in module docstring

**Example:**
```python
async def add_episode(self, content: str, session_id: str) -> None:
    """Add episode to graph (LLM extraction currently disabled).
    
    NOTE: This method uses Gemini API for LLM-powered entity extraction,
    which is currently rate-limited on free tier. Use upsert_entity()
    for manual entity creation as a workaround.
    """
    try:
        await self.graphiti.add_episode(
            content=content,
            metadata={"session_id": session_id}
        )
    except Exception as e:
        if "503" in str(e) or "rate" in str(e).lower():
            logger.warning(
                f"Graphiti add_episode rate limited: {e}. "
                "Use upsert_entity() for manual entity creation."
            )
        else:
            logger.error(f"Graphiti add_episode failed: {e}")
```

### Cluster Retrieval Errors

**Scenario:** Cluster search fails (FalkorDB down, query error)

**Handling:**
1. Catch exception in `get_cluster_session_ids`
2. Log error
3. Return empty list `[]`
4. Calling code (memory engine) falls back to general vector search

**Example:**
```python
async def get_cluster_session_ids(
    self, entity_names: List[str], depth: int = 2
) -> List[str]:
    if not self.is_initialized:
        logger.warning("GraphLTM not initialized, returning empty cluster")
        return []
    
    try:
        # Perform Graphiti search and traversal
        results = await self.graphiti.search(...)
        return [r["session_id"] for r in results][:50]
    except Exception as e:
        logger.error(f"Cluster retrieval failed: {e}")
        return []
```

### Missing Configuration

**Scenario:** FALKORDB_HOST not set in environment

**Handling:**
1. Settings uses default "localhost"
2. Connection attempt fails
3. `is_initialized` remains False
4. Health checks report "not_configured"
5. App continues with degraded L2 functionality

## Testing Strategy

### Unit Tests

**Test File:** `tests/test_graph_ltm.py`

**Test Cases:**

1. **test_initialize_success()**
   - Mock FalkorDB connection
   - Call initialize()
   - Assert is_initialized = True

2. **test_initialize_failure()**
   - Mock FalkorDB connection to fail
   - Call initialize()
   - Assert is_initialized = False
   - Assert error logged

3. **test_upsert_entity()**
   - Mock Graphiti client
   - Call upsert_entity with test data
   - Verify entity created in mock

4. **test_get_all_entity_names()**
   - Mock Graphiti search returning test entities
   - Call get_all_entity_names()
   - Assert returned list matches mock data

5. **test_get_cluster_session_ids()**
   - Mock Graphiti search and traversal
   - Call get_cluster_session_ids with test entities
   - Verify returned session IDs match expected

6. **test_link_session_to_entities()**
   - Mock Graphiti client
   - Call link_session_to_entities with test data
   - Verify session node and edges created

7. **test_health_check_success()**
   - Mock FalkorDB healthy
   - Call health_check()
   - Assert returns True

8. **test_health_check_failure()**
   - Mock FalkorDB down
   - Call health_check()
   - Assert returns False

9. **test_add_episode_rate_limited()**
   - Mock Graphiti add_episode to raise 503 error
   - Call add_episode()
   - Verify graceful handling and warning log

10. **test_cluster_retrieval_not_initialized()**
    - Set is_initialized = False
    - Call get_cluster_session_ids()
    - Assert returns empty list

### Integration Tests

**Test File:** `tests/integration/test_falkordb_integration.py`

**Prerequisites:** FalkorDB running on localhost:6379

**Test Cases:**

1. **test_connect_to_falkordb()**
   - Initialize graph_ltm with real FalkorDB
   - Verify connection succeeds
   - Verify is_initialized = True

2. **test_entity_creation_and_retrieval()**
   - Create test entity via upsert_entity()
   - Retrieve via get_all_entity_names()
   - Verify entity appears in results

3. **test_session_entity_linking()**
   - Create test entities
   - Link session to entities
   - Query cluster sessions
   - Verify session ID returned

4. **test_focus_tracking()**
   - Update current focus
   - Retrieve current focus
   - Verify focus matches

5. **test_search_functionality()**
   - Create test entities
   - Perform search query
   - Verify relevant results returned

6. **test_end_to_end_memory_flow()**
   - Save session with entities via memory_engine
   - Retrieve context via get_context_for_session
   - Verify entities spotted and context retrieved

### End-to-End Tests

**Test File:** `tests/e2e/test_memory_pipeline_falkordb.py`

**Test Cases:**

1. **test_full_memory_pipeline()**
   - Start session
   - Save session with entities
   - Verify L2 (FalkorDB), L3 (Pinecone), L4 (MongoDB) all updated
   - Retrieve context in new session
   - Verify cluster retrieval works

2. **test_prefetch_engine_with_falkordb()**
   - Spot entities in message
   - Verify prefetch queue populated
   - Wait for prefetch completion
   - Verify entity context cached in Redis

3. **test_health_checks()**
   - Call deep health check endpoint
   - Verify FalkorDB status reported
   - Verify no Neo4j status reported

## Implementation Notes

### Migration Steps

1. **Phase 1: Create graph_ltm.py**
   - Implement all methods with FalkorDB/Graphiti
   - Add module docstring documenting Graphiti limitations
   - Export singleton

2. **Phase 2: Update Configuration**
   - Add FalkorDB settings to config.py
   - Add FalkorDB to .env.template
   - Remove Neo4j settings

3. **Phase 3: Update Integrations**
   - Update memory_engine.py imports and calls
   - Update prefetch_engine.py imports
   - Update database.py (remove Neo4j)
   - Update health.py

4. **Phase 4: Remove Neo4j Files**
   - Delete memory/l2_graph.py
   - Delete memory/schema_init.py
   - Delete initialize_graph.py
   - Update requirements.txt

5. **Phase 5: Update Tests**
   - Update test imports
   - Add new graph_ltm tests
   - Add integration tests

6. **Phase 6: Verify End-to-End**
   - Run full test suite
   - Test memory pipeline manually
   - Verify health checks
   - Document any issues

### Backward Compatibility

The GraphLTM class maintains the same method signatures as L2Graph:

**Method Signature Compatibility:**

| L2Graph (Neo4j) | GraphLTM (FalkorDB) | Compatible? |
|-----------------|---------------------|-------------|
| `connect()` | `initialize()` | Different name, handled in memory_engine |
| `get_all_entity_names()` | `get_all_entity_names()` | ✅ Yes |
| `get_current_focus()` | `get_current_focus()` | ✅ Yes |
| `get_cluster_session_ids(names, depth)` | `get_cluster_session_ids(names, depth)` | ✅ Yes |
| `upsert_entity(name, type, desc, rel)` | `upsert_entity(name, type, desc, rel)` | ✅ Yes |
| `link_session_to_entities(...)` | `link_session_to_entities(...)` | ✅ Yes |
| `update_current_focus(entity)` | `update_current_focus(entity)` | ✅ Yes |
| `disconnect()` | `disconnect()` | ✅ Yes |

**Return Type Compatibility:**

- `get_all_entity_names()`: Returns `List[str]` (same)
- `get_current_focus()`: Returns `Dict` with same keys (same)
- `get_cluster_session_ids()`: Returns `List[str]` (same)
- All void methods remain void

**Only Breaking Change:**
- `connect()` → `initialize()` - handled explicitly in memory_engine.py

### Performance Considerations

**FalkorDB vs Neo4j:**
- FalkorDB is Redis-based, offering sub-millisecond latency for simple queries
- Neo4j Aura has network latency (cloud-hosted)
- FalkorDB is local, reducing network overhead
- Cluster retrieval may be faster with FalkorDB for small graphs (<10k entities)

**Caching Strategy:**
- Continue using Redis L1 cache for entity context
- Prefetch engine reduces FalkorDB queries
- Known entities list cached in memory (_known_entities)

**Query Optimization:**
- Limit cluster retrieval to 50 sessions max
- Use depth parameter to control traversal (default 2)
- Cache Graphiti search results when possible

### Deployment Considerations

**FalkorDB Installation:**
```bash
# Docker deployment
docker run -p 6379:6379 falkordb/falkordb:latest

# Or use existing Redis with FalkorDB module
# (requires Redis with module support)
```

**Environment Setup:**
```bash
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_DATABASE=asta_graph
```

**Migration Checklist:**
- [ ] FalkorDB running and accessible
- [ ] Dependencies installed (falkordb, graphiti-core)
- [ ] Configuration updated
- [ ] Neo4j credentials removed from .env
- [ ] Tests passing
- [ ] Health checks showing FalkorDB status
- [ ] End-to-end memory pipeline working

### Documentation Updates

**Module Docstring for graph_ltm.py:**
```python
"""
ASTA Memory Layer - L2 Knowledge Graph (FalkorDB with Graphiti)
──────────────────────────────────────────────────────────────

This is the L2 knowledge graph layer using FalkorDB with Graphiti.
Manages entity relationships and cluster-based session retrieval.

Architecture:
- FalkorDB: Redis-based graph database (replaces Neo4j)
- Graphiti: LLM-powered knowledge graph library

Known Limitations:
- Graphiti's add_episode() LLM extraction is disabled due to Gemini API
  rate limits on free tier (503 errors). Use upsert_entity() for manual
  entity creation as a workaround.
- Search and graph operations work normally
- Entity relationship management fully functional

Configuration:
Set these environment variables:
- FALKORDB_HOST (default: localhost)
- FALKORDB_PORT (default: 6379)
- FALKORDB_DATABASE (default: asta_graph)
- FALKORDB_USERNAME (optional)
- FALKORDB_PASSWORD (optional)
"""
```

**README Update:**
Add section documenting FalkorDB setup and migration from Neo4j.

## Dependencies

### Add to requirements.txt

```
falkordb>=4.0.0
graphiti-core>=0.3.0
```

### Remove from requirements.txt

```
neo4j  # DELETE THIS LINE
```

### Verify Compatibility

Graphiti requires:
- Python 3.9+
- Redis (for FalkorDB)
- LLM API (Gemini, OpenAI, etc.) - currently using Gemini

FalkorDB requires:
- Redis 6.2+
- FalkorDB module loaded

## Risk Mitigation

### Risk 1: FalkorDB Not Configured

**Mitigation:**
- Graceful degradation: app runs with L2 disabled
- Clear error messages in logs
- Health checks report configuration status
- Documentation includes setup instructions

### Risk 2: Graphiti Rate Limiting

**Mitigation:**
- Document limitation in module docstring
- Provide manual workaround (upsert_entity)
- Log warnings when rate limits hit
- Consider upgrading Gemini API tier in future

### Risk 3: Data Loss During Migration

**Mitigation:**
- No data loss - L2 (graph) is ephemeral and rebuilt from L4 (MongoDB)
- All permanent data lives in L4
- Neo4j data not migrated (transient cluster relationships)
- After migration, graph rebuilds from sessions

### Risk 4: Performance Regression

**Mitigation:**
- Monitor cluster retrieval latency
- Compare Neo4j vs FalkorDB query times
- Add logging/metrics to critical paths
- Optimize Graphiti queries if needed

### Risk 5: API Incompatibility

**Mitigation:**
- Maintain same method signatures
- Handle connect() → initialize() explicitly
- Return same data structures
- Add compatibility layer if needed

