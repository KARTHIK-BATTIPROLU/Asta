# Implementation Plan: Remove Neo4j and Migrate to FalkorDB/Graphiti

## Overview

This implementation plan breaks down the migration from Neo4j to FalkorDB/Graphiti into discrete, testable tasks. The approach is:

1. Create the new FalkorDB/Graphiti implementation first
2. Update configuration and dependencies
3. Update all integration points
4. Remove Neo4j code
5. Update tests and verify end-to-end functionality

Each task builds incrementally, ensuring the system remains in a working state throughout the migration.

## Tasks

- [x] 1. Add FalkorDB/Graphiti Dependencies
  - Add `falkordb>=4.0.0` to requirements.txt
  - Add `graphiti-core>=0.3.0` to requirements.txt
  - Remove `neo4j` from requirements.txt
  - Install dependencies with `pip install -r requirements.txt`
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 2. Create GraphLTM Implementation
  - [x] 2.1 Create backend/app/services/memory/graph_ltm.py file
    - Define GraphLTM class with __init__ method
    - Initialize instance variables (graphiti, is_initialized, _known_entities, _current_focus)
    - Add comprehensive module docstring documenting FalkorDB/Graphiti and known Gemini API limitations
    - _Requirements: 2.1, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 2.2 Implement initialize() method
    - Connect to FalkorDB using settings.FALKORDB_HOST, FALKORDB_PORT, FALKORDB_DATABASE
    - Create Graphiti client instance
    - Set is_initialized flag on success
    - Handle connection errors gracefully (log and set is_initialized=False)
    - _Requirements: 2.2, 2.10_

  - [x] 2.3 Implement health_check() method
    - Verify FalkorDB connectivity with simple query
    - Return True if connected, False otherwise
    - Handle exceptions gracefully
    - _Requirements: 2.9_

  - [x] 2.4 Implement get_all_entity_names() method
    - Query Graphiti for all entity nodes
    - Return list of entity name strings
    - Cache results in _known_entities
    - Handle not_initialized state (return empty list)
    - _Requirements: 2.3, 10.4_

  - [ ] 2.5 Implement get_current_focus() method
    - Return dict with current_focus, last_active_project, last_active keys
    - Use instance variable or retrieve from FalkorDB
    - Match return format of Neo4j implementation
    - _Requirements: 2.4, 10.5_

  - [x] 2.6 Implement upsert_entity() method
    - Accept name, entity_type, description, relation parameters
    - Create or update entity node in FalkorDB via Graphiti
    - Store entity metadata (type, description, relation)
    - Update _known_entities cache
    - Handle errors and log
    - _Requirements: 2.6, 10.1_

  - [x] 2.7 Implement get_cluster_session_ids() method
    - Accept entity_names list and depth parameter (default 2)
    - Guard against None or empty input (return empty list)
    - Use Graphiti search to find entities matching entity_names
    - Traverse relationships up to depth hops
    - Extract session_ids from connected session nodes
    - Limit results to 50 sessions max
    - Return list of session_id strings
    - Handle not_initialized state and errors (return empty list)
    - _Requirements: 2.5, 10.3, 12.4, 12.5_

  - [x] 2.8 Implement link_session_to_entities() method
    - Accept session_id, entities list, workflow_type, summary_snippet parameters
    - Create session node in FalkorDB with metadata
    - Create edges from session node to each entity node
    - Use COVERS relationship type
    - Handle errors and log
    - _Requirements: 2.7, 10.2, 12.1, 12.2, 12.3_

  - [x] 2.9 Implement update_current_focus() method
    - Accept entity_name parameter
    - Update _current_focus instance variable or FalkorDB
    - Update last_active timestamp
    - _Requirements: 2.8_

  - [x] 2.10 Implement search() method
    - Accept query string and limit parameter (default 10)
    - Use Graphiti search API
    - Return list of matching entities with metadata
    - Handle errors and return empty list
    - _Requirements: 2.11_

  - [x] 2.11 Implement add_episode() method (with rate limit handling)
    - Accept content and session_id parameters
    - Attempt Graphiti add_episode with LLM extraction
    - Catch rate limit errors (503, "rate" in message)
    - Log warning about Gemini API limitation and workaround
    - Handle other errors and log
    - _Requirements: 2.12, 9.1_

  - [x] 2.12 Implement disconnect() method
    - Gracefully close Graphiti client
    - Clean up resources
    - Set is_initialized = False
    - _Requirements: 10.1_

  - [x] 2.13 Export singleton instance
    - Create module-level singleton: `graph_ltm = GraphLTM()`
    - _Requirements: 2.1_

- [x] 3. Update Configuration Files
  - [x] 3.1 Update backend/app/config.py
    - Add FALKORDB_HOST: str = "localhost"
    - Add FALKORDB_PORT: int = 6379
    - Add FALKORDB_USERNAME: str = ""
    - Add FALKORDB_PASSWORD: str = ""
    - Add FALKORDB_DATABASE: str = "asta_graph"
    - Remove NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_

  - [x] 3.2 Update .env.template
    - Add FalkorDB configuration section with example values
    - Remove all NEO4J_* variables
    - Remove AURA_INSTANCEID and AURA_INSTANCENAME
    - _Requirements: 3.6, 3.8_

- [ ] 4. Update Memory Engine Integration
  - [ ] 4.1 Update memory/memory_engine.py imports
    - Replace `from memory.l2_graph import l2_graph` with `from backend.app.services.memory.graph_ltm import graph_ltm`
    - _Requirements: 4.1_

  - [ ] 4.2 Update connect_all() method
    - Change layer tuple from ("L2_neo4j", l2_graph) to ("L2_graphiti", graph_ltm)
    - Call `await layer.initialize()` instead of `await layer.connect()` for L2_graphiti
    - _Requirements: 4.8_

  - [ ] 4.3 Update all L2 method calls
    - Ensure all calls use graph_ltm instead of l2_graph (variable rename)
    - Verify method signatures match: get_all_entity_names(), get_current_focus(), get_cluster_session_ids(), upsert_entity(), link_session_to_entities(), update_current_focus()
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ] 4.4 Update disconnect_all() method
    - Call graph_ltm.disconnect() instead of l2_graph.disconnect()
    - _Requirements: 4.9_

- [ ] 5. Update Prefetch Engine Integration
  - [ ] 5.1 Update memory/prefetch_engine.py imports
    - In _import_dependencies() method, import from backend.app.services.memory.graph_ltm instead of memory.l2_graph
    - Assign self._l2_graph = graph_ltm
    - _Requirements: 5.1_

  - [ ] 5.2 Verify prefetch method calls
    - Confirm calls to self._l2_graph.get_all_entity_names() and self._l2_graph.get_cluster_session_ids() work with graph_ltm
    - _Requirements: 5.2, 5.3, 5.4_

- [ ] 6. Checkpoint - Verify New Implementation
  - Ensure all tests pass, run basic smoke test of graph_ltm initialization
  - Ask the user if questions arise

- [ ] 7. Update Database Manager
  - [ ] 7.1 Remove Neo4j imports from backend/app/db/database.py
    - Delete `from neo4j import AsyncGraphDatabase` import statement
    - _Requirements: 6.2_

  - [ ] 7.2 Remove Neo4j driver initialization
    - Delete `self.neo4j_driver = None` from __new__ method
    - _Requirements: 6.2_

  - [ ] 7.3 Remove Neo4j connection logic from connect() method
    - Delete entire "2. Neo4j Aura Connection" section
    - _Requirements: 6.1_

  - [ ] 7.4 Remove Neo4j health check from ping() method
    - Delete "Ping Neo4j" section
    - _Requirements: 6.3_

  - [ ] 7.5 Remove Neo4j disconnect logic from disconnect() method
    - Delete neo4j_driver close logic
    - _Requirements: 6.4_

- [ ] 8. Update Health Check Endpoints
  - [ ] 8.1 Remove Neo4j health check from backend/app/api/health.py
    - Delete entire "Check Neo4j" section from deep_health_check()
    - _Requirements: 7.2_

  - [ ] 8.2 Add FalkorDB health check to backend/app/api/health.py
    - Import graph_ltm from backend.app.services.memory.graph_ltm
    - Check is_initialized flag
    - Call graph_ltm.health_check() if initialized
    - Return appropriate status dict (ok, not_initialized, error)
    - Set overall status to degraded if FalkorDB fails
    - _Requirements: 7.1, 7.3, 7.4, 7.5_

- [ ] 9. Remove Neo4j Files
  - [ ] 9.1 Delete memory/l2_graph.py file
    - Remove entire 318-line Neo4j implementation
    - _Requirements: 1.1_

  - [ ] 9.2 Delete memory/schema_init.py file
    - Remove Neo4j schema initialization script
    - _Requirements: 1.2_

  - [ ] 9.3 Delete initialize_graph.py file (if exists in root)
    - Remove Neo4j setup script
    - _Requirements: 1.3_

- [ ] 10. Update Test Files
  - [ ] 10.1 Create tests/test_graph_ltm.py
    - Write unit test for initialize() success
    - Write unit test for initialize() failure
    - Write unit test for upsert_entity()
    - Write unit test for get_all_entity_names()
    - Write unit test for get_cluster_session_ids()
    - Write unit test for link_session_to_entities()
    - Write unit test for health_check() success
    - Write unit test for health_check() failure
    - Write unit test for add_episode() rate limiting
    - Write unit test for cluster_retrieval_not_initialized()
    - Use mocks for FalkorDB/Graphiti client
    - _Requirements: 8.1, 8.2, 10.1_

  - [ ] 10.2 Update existing test files
    - Find all test files importing from memory.l2_graph
    - Replace imports with backend.app.services.memory.graph_ltm
    - Update method calls to use graph_ltm instead of l2_graph
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 10.3 Create integration tests
    - Create tests/integration/test_falkordb_integration.py
    - Test real FalkorDB connection (requires FalkorDB running)
    - Test entity creation and retrieval
    - Test session-entity linking
    - Test focus tracking
    - Test search functionality
    - _Requirements: 8.1, 10.1_

  - [ ]* 10.4 Create end-to-end tests
    - Create tests/e2e/test_memory_pipeline_falkordb.py
    - Test full memory pipeline (save → retrieve)
    - Test prefetch engine with FalkorDB
    - Test health checks reporting FalkorDB status
    - _Requirements: 8.1, 10.1_

- [ ] 11. Checkpoint - Verify Tests Pass
  - Run full test suite with pytest
  - Ensure no Neo4j dependencies remain
  - Ask the user if questions arise

- [ ] 12. Manual End-to-End Verification
  - [ ] 12.1 Verify FalkorDB connectivity
    - Start FalkorDB (Docker: `docker run -p 6379:6379 falkordb/falkordb:latest`)
    - Run health check endpoint: GET /health/deep
    - Verify FalkorDB status is "ok"
    - _Requirements: 7.1, 7.3_

  - [ ] 12.2 Test memory pipeline manually
    - Start ASTA backend
    - Create a test conversation with entities (e.g., mention "ASTA project" and "Python")
    - Save session via memory_engine.save_session()
    - Verify entities created in FalkorDB via graph_ltm.get_all_entity_names()
    - Start new session mentioning same entities
    - Retrieve context via memory_engine.get_context_for_session()
    - Verify cluster retrieval returns related sessions
    - _Requirements: 10.2, 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ] 12.3 Test prefetch engine
    - Send message mentioning known entity
    - Verify prefetch queue populated
    - Wait for prefetch worker to process
    - Verify entity context cached in Redis L1
    - _Requirements: 5.2, 5.3, 5.4_

  - [ ] 12.4 Verify no Neo4j references remain
    - Search codebase for "neo4j" (case-insensitive): `grep -ri "neo4j" --exclude-dir=venv --exclude-dir=.git`
    - Search for "l2_graph" imports: `grep -r "from memory.l2_graph" --exclude-dir=venv`
    - Verify no matches in Python source files
    - _Requirements: 1.4, 1.5, 1.6, 1.7_

- [ ] 13. Update Documentation
  - [ ] 13.1 Update README.md (if applicable)
    - Add FalkorDB setup instructions
    - Document Graphiti limitations (add_episode rate limiting)
    - Explain manual entity creation workaround
    - Remove Neo4j references
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 13.2 Add migration notes
    - Document that Neo4j data is not migrated (transient)
    - Explain that L2 graph rebuilds from L4 MongoDB sessions
    - Note performance considerations (FalkorDB local vs Neo4j cloud)
    - _Requirements: 9.1_

- [ ] 14. Final Checkpoint - Production Readiness
  - All tests passing
  - Health checks showing FalkorDB status
  - End-to-end memory pipeline working
  - Documentation updated
  - Ask the user if questions arise

## Notes

- Tasks marked with `*` are optional integration/E2E tests (can be skipped for faster MVP)
- Each task builds incrementally on previous tasks
- Checkpoints ensure validation at critical milestones
- FalkorDB must be running for integration/E2E tests and manual verification
- No data migration needed - L2 graph is transient and rebuilds from L4 (MongoDB)
- The migration maintains API compatibility with minimal changes to calling code

