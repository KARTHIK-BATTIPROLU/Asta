# Requirements Document: Memory Layer Verification and Testing

## Introduction

This specification defines the requirements for comprehensive verification and testing of ASTA's 5-layer memory architecture on the face-and-soul branch. The memory system orchestrates data flow across L0 (in-flight context), L1 (Redis hot cache), L1.5 (speculative prefetch), L2 (FalkorDB knowledge graph via Graphiti), L3 (Pinecone vector store), and L4 (MongoDB cold store). The current implementation has identified issues preventing full verification: a HuggingFace Hub import error blocking test execution, L2 graph layer's LLM extraction disabled due to Gemini API token limits, and lack of end-to-end test coverage for the complete memory pipeline.

## Glossary

- **Memory_Engine**: The master orchestrator that coordinates all memory operations across the 5-layer architecture
- **L0_Layer**: In-flight context stored in LangGraph state during active execution
- **L1_Cache**: Redis hot cache layer for entities, session context, and retrieved results
- **L1_5_Prefetch**: Speculative prefetch engine that pre-loads entity context in background
- **L2_Graph**: FalkorDB knowledge graph accessed via Graphiti for entity relationships
- **L3_Vectors**: Pinecone vector store for semantic search using MiniLM embeddings
- **L4_Store**: MongoDB cold storage for full sessions, permanent memory, and entities
- **Session**: A complete conversation or workflow execution with unique session_id
- **Turn**: A single request-response cycle within a session, identified by turn_id
- **Entity**: A named concept, topic, or object extracted from conversation text
- **Embedding_Function**: The unified MiniLM-L6-v2 sentence transformer producing 384-dimensional vectors
- **Health_Check**: A live connectivity test that verifies a layer is currently reachable
- **Memory_Pipeline**: The complete flow: write (save_session) and read (get_context_for_session)

## Requirements

### Requirement 1: Fix Test Infrastructure Blocking Issues

**User Story:** As a developer, I want the test infrastructure to run without import errors, so that I can verify memory layer functionality.

#### Acceptance Criteria

1. WHEN the test script imports memory modules, THE System SHALL NOT raise import errors related to huggingface_hub
2. WHEN running tests in the venv environment, THE System SHALL have all required dependencies installed correctly
3. WHEN importing from memory.embeddings, THE Embedding_Function SHALL load without HuggingFace Hub connectivity issues
4. THE System SHALL document any environment-specific requirements or workarounds needed for test execution

### Requirement 2: Verify L1 Redis Cache Layer

**User Story:** As a developer, I want to verify L1 cache operations, so that I can ensure hot data retrieval is working correctly.

#### Acceptance Criteria

1. WHEN Memory_Engine calls l1_cache.connect(), THE L1_Cache SHALL successfully connect to Redis and respond to ping
2. WHEN starting a session, THE L1_Cache SHALL create an active_session key with workflow_type and start_time
3. WHEN caching entity context, THE L1_Cache SHALL store related sessions with TTL according to REDIS_TTL_ENTITY setting
4. WHEN retrieving entity context, THE L1_Cache SHALL increment hit_count and return cached sessions
5. WHEN caching retrieved context for a session, THE L1_Cache SHALL store the complete context list with session-specific TTL
6. WHEN invalidating entity context, THE L1_Cache SHALL remove the cached data for that entity
7. WHEN performing health_check, THE L1_Cache SHALL return True if Redis responds to ping, False otherwise

### Requirement 3: Verify L2 FalkorDB Graph Layer

**User Story:** As a developer, I want to verify L2 graph operations within current API limitations, so that I can ensure the knowledge graph is correctly configured even though LLM extraction is disabled.

#### Acceptance Criteria

1. WHEN Memory_Engine calls graph_ltm.initialize(), THE L2_Graph SHALL connect to FalkorDB using configured credentials
2. WHEN performing a search query, THE L2_Graph SHALL return relevant edges in the expected format (list of dicts with "text" and "ts" fields)
3. WHEN add_episode is called, THE L2_Graph SHALL log that extraction was skipped due to API limits but not raise errors
4. THE L2_Graph SHALL be clearly documented as having LLM extraction disabled until API key upgrade
5. WHEN health_check is implemented for L2, THE L2_Graph SHALL verify FalkorDB connectivity

### Requirement 4: Verify L3 Pinecone Vector Layer

**User Story:** As a developer, I want to verify L3 vector operations, so that I can ensure semantic search is working correctly.

#### Acceptance Criteria

1. WHEN Memory_Engine calls l3_vectors.connect(), THE L3_Vectors SHALL initialize Pinecone client and verify index exists or create it
2. WHEN embedding text, THE L3_Vectors SHALL use the unified MiniLM Embedding_Function to produce 384-dimensional vectors
3. WHEN upserting a session vector, THE L3_Vectors SHALL store the vector with session_id, turn_id, and metadata
4. WHEN searching by text, THE L3_Vectors SHALL embed the query and return top_k results with scores and metadata
5. WHEN searching by entity, THE L3_Vectors SHALL filter results by entity_names metadata field
6. WHEN performing health_check, THE L3_Vectors SHALL verify Pinecone index is reachable via describe_index_stats

### Requirement 5: Verify L4 MongoDB Store Layer

**User Story:** As a developer, I want to verify L4 storage operations, so that I can ensure full session data and permanent memories are persisted correctly.

#### Acceptance Criteria

1. WHEN Memory_Engine calls l4_store.connect(), THE L4_Store SHALL connect to MongoDB and create required indexes
2. WHEN saving a session, THE L4_Store SHALL store the complete document with session_id, turn_id, metadata, and raw_transcript
3. WHEN retrieving sessions by IDs, THE L4_Store SHALL return all matching turn documents (multiple turns per session_id allowed)
4. WHEN saving permanent memory, THE L4_Store SHALL create a unique memory_id and store content with tags
5. WHEN retrieving permanent memories by tags, THE L4_Store SHALL return all documents where tags array intersects with query tags
6. WHEN saving entities, THE L4_Store SHALL upsert by (name, entity_type) unique key
7. WHEN performing health_check, THE L4_Store SHALL verify MongoDB responds to admin ping command

### Requirement 6: Verify L1.5 Prefetch Engine

**User Story:** As a developer, I want to verify prefetch operations, so that I can ensure background entity loading is functioning correctly.

#### Acceptance Criteria

1. WHEN Memory_Engine calls prefetch_engine.start(), THE L1_5_Prefetch SHALL initialize the bounded queue and start the background worker
2. WHEN on_message is called with user text, THE L1_5_Prefetch SHALL spot entities and queue uncached entities for prefetch
3. WHEN the prefetch worker processes a queue item, THE L1_5_Prefetch SHALL retrieve context from L3/L4 and cache in L1
4. WHEN the prefetch queue is full, THE L1_5_Prefetch SHALL skip new items and log a warning (backpressure handling)
5. WHEN performing stop, THE L1_5_Prefetch SHALL gracefully cancel the worker task
6. WHEN get_queue_size is called, THE L1_5_Prefetch SHALL return the current number of queued items

### Requirement 7: Verify End-to-End Memory Pipeline Write Path

**User Story:** As a developer, I want to verify the complete write pipeline, so that I can ensure session data flows correctly through all layers.

#### Acceptance Criteria

1. WHEN Memory_Engine.save_session is called with session data, THE Memory_Engine SHALL extract entities and summary
2. WHEN saving to L4, THE Memory_Engine SHALL store the complete session document with turn_id
3. WHEN saving to L3, THE Memory_Engine SHALL upsert a vector with ID format "session_id:turn_id"
4. WHEN saving to L2, THE Memory_Engine SHALL call graph_ltm.add_episode (even if LLM extraction is disabled)
5. WHEN saving entities to L4, THE Memory_Engine SHALL upsert each extracted entity
6. WHEN save_session completes, THE Memory_Engine SHALL invalidate entity caches and flush session keys from L1
7. WHEN any layer write fails, THE Memory_Engine SHALL log the error but continue with other layers (error isolation)

### Requirement 8: Verify End-to-End Memory Pipeline Read Path

**User Story:** As a developer, I want to verify the complete read pipeline, so that I can ensure context retrieval works correctly across all layers.

#### Acceptance Criteria

1. WHEN Memory_Engine.get_context_for_session is called, THE Memory_Engine SHALL first check L1 for cached retrieved context
2. WHEN retrieved context is cached in L1, THE Memory_Engine SHALL return immediately with from_cache=True
3. WHEN context is not cached, THE Memory_Engine SHALL spot entities in user_input
4. WHEN entities are spotted, THE Memory_Engine SHALL check L1 entity cache for each entity
5. WHEN entity context is not cached, THE Memory_Engine SHALL perform L2 cluster search then L3 vector search then L4 fetch
6. WHEN no entities are spotted, THE Memory_Engine SHALL fall back to general L3 vector search plus L4 fetch
7. WHEN retrieval completes, THE Memory_Engine SHALL cache the result in L1 for the session
8. WHEN retrieval completes, THE Memory_Engine SHALL fire prefetch for spotted entities (non-blocking)

### Requirement 9: Verify Health Check Aggregation

**User Story:** As a developer, I want to verify the aggregated health check, so that I can monitor all layer connectivity in one call.

#### Acceptance Criteria

1. WHEN Memory_Engine.health_check is called, THE Memory_Engine SHALL perform live health checks on all layers in parallel
2. WHEN all layers are healthy, THE Memory_Engine SHALL return a dict with all layer statuses set to True
3. WHEN any layer is unhealthy, THE Memory_Engine SHALL return False for that layer without crashing the health check
4. THE Memory_Engine SHALL include prefetch_queue_size in the health check response
5. WHEN health_check encounters an exception, THE Memory_Engine SHALL return all statuses as False and log the error

### Requirement 10: Verify Permanent Memory Operations

**User Story:** As a developer, I want to verify permanent memory storage and recall, so that I can ensure explicitly saved memories persist correctly.

#### Acceptance Criteria

1. WHEN Memory_Engine.remember is called with content and tags, THE Memory_Engine SHALL save to L4 permanent_memory collection
2. WHEN saving permanent memory, THE Memory_Engine SHALL also upsert to L3 with vector ID format "permanent_{memory_id}"
3. WHEN Memory_Engine.recall is called with a query, THE Memory_Engine SHALL perform L3 vector search filtered by "permanent_" prefix
4. WHEN permanent memories are found, THE Memory_Engine SHALL increment recalled_count in L4 for each memory
5. WHEN recall completes, THE Memory_Engine SHALL return a list of permanent memory documents

### Requirement 11: Verify Context Formatting

**User Story:** As a developer, I want to verify context formatting, so that I can ensure retrieved sessions are properly formatted for LLM injection.

#### Acceptance Criteria

1. WHEN format_context_for_prompt is called with empty sessions list, THE Memory_Engine SHALL return an empty string
2. WHEN format_context_for_prompt is called with sessions, THE Memory_Engine SHALL include a "RELEVANT PAST CONTEXT" header
3. WHEN formatting each session, THE Memory_Engine SHALL include workflow_type, date, summary, and entities
4. WHEN a session has a list-type summary, THE Memory_Engine SHALL join it into a single string
5. WHEN a session has None entities, THE Memory_Engine SHALL handle it gracefully without errors

### Requirement 12: Create Comprehensive Test Suite

**User Story:** As a developer, I want a comprehensive test suite, so that I can verify all memory layer operations systematically.

#### Acceptance Criteria

1. THE Test_Suite SHALL include unit tests for each layer (L1, L2, L3, L4, L1.5) testing their core operations in isolation
2. THE Test_Suite SHALL include integration tests for the complete write pipeline (save_session)
3. THE Test_Suite SHALL include integration tests for the complete read pipeline (get_context_for_session)
4. THE Test_Suite SHALL include health check tests verifying all layers respond correctly
5. THE Test_Suite SHALL include error handling tests verifying graceful failure when layers are unavailable
6. THE Test_Suite SHALL include tests for permanent memory operations (remember/recall)
7. THE Test_Suite SHALL be runnable with a single command and report clear pass/fail results
8. THE Test_Suite SHALL use async test fixtures to manage layer connections and cleanup

### Requirement 13: Document Current Limitations and Workarounds

**User Story:** As a developer, I want current limitations clearly documented, so that I understand what functionality is available and what requires future work.

#### Acceptance Criteria

1. THE Documentation SHALL clearly state that L2 LLM extraction is disabled due to Gemini API token limits
2. THE Documentation SHALL explain the HuggingFace Hub import issue and its resolution
3. THE Documentation SHALL document which L2 operations are functional (search, initialization) and which are disabled (add_episode with extraction)
4. THE Documentation SHALL provide instructions for upgrading the API key to re-enable L2 LLM extraction
5. THE Documentation SHALL document any environment setup required for test execution
