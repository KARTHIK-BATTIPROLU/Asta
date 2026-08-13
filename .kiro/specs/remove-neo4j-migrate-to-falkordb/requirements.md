# Requirements Document

## Introduction

This document specifies the requirements for completely removing Neo4j from the ASTA memory architecture and migrating all L2 graph layer functionality to FalkorDB with Graphiti. The current system has both Neo4j (`memory/l2_graph.py`) and references to FalkorDB/Graphiti (`graph_ltm`), causing confusion and non-functional L2 memory operations. This migration will establish FalkorDB/Graphiti as the single source of truth for the L2 knowledge graph layer.

## Glossary

- **System**: The ASTA memory architecture
- **L2_Layer**: The knowledge graph layer responsible for entity relationships and cluster-based retrieval
- **Neo4j**: The current graph database being removed
- **FalkorDB**: The Redis-based graph database replacing Neo4j
- **Graphiti**: The LLM-powered knowledge graph library built on FalkorDB
- **Memory_Engine**: The master orchestrator for all memory operations
- **Prefetch_Engine**: Background service that pre-fetches entity context
- **Entity**: A named concept tracked in the knowledge graph (project, skill, person, topic, tool, commitment)
- **Session**: A conversation turn or interaction that may reference entities
- **Cluster_Retrieval**: Finding sessions connected to entities within a relationship depth
- **Health_Check**: Verification endpoint that tests database connectivity

## Requirements

### Requirement 1: Remove Neo4j Implementation

**User Story:** As a developer, I want all Neo4j code removed, so that the codebase has no conflicting graph database implementations.

#### Acceptance Criteria

1. THE System SHALL NOT contain the file `memory/l2_graph.py`
2. THE System SHALL NOT contain the file `memory/schema_init.py`
3. THE System SHALL NOT contain the file `initialize_graph.py`
4. THE System SHALL NOT import neo4j library in any Python file
5. THE System SHALL NOT contain neo4j in requirements.txt dependencies
6. THE System SHALL NOT contain Neo4j configuration parameters in config.py
7. THE System SHALL NOT contain Neo4j configuration parameters in .env.template

### Requirement 2: Create FalkorDB/Graphiti L2 Implementation

**User Story:** As a developer, I want a complete FalkorDB/Graphiti implementation, so that all L2 graph operations work with the new database.

#### Acceptance Criteria

1. THE System SHALL contain file `backend/app/services/memory/graph_ltm.py` with Graphiti integration
2. WHEN the system initializes THEN the System SHALL connect to FalkorDB using Graphiti client
3. THE Graph_LTM SHALL implement method `get_all_entity_names()` returning list of known entity names
4. THE Graph_LTM SHALL implement method `get_current_focus()` returning the current focus entity
5. THE Graph_LTM SHALL implement method `get_cluster_session_ids(entity_names, depth)` returning related session IDs
6. THE Graph_LTM SHALL implement method `upsert_entity(name, type, description, relation)` for creating/updating entities
7. THE Graph_LTM SHALL implement method `link_session_to_entities(session_id, entities, workflow_type, summary)` for linking sessions to entities
8. THE Graph_LTM SHALL implement method `update_current_focus(entity_name)` for tracking current work focus
9. THE Graph_LTM SHALL implement method `health_check()` for verifying FalkorDB connectivity
10. THE Graph_LTM SHALL implement method `initialize()` for initializing the Graphiti client
11. THE Graph_LTM SHALL implement method `search(query)` for searching entities in the graph
12. WHEN add_episode is called AND Gemini API is rate-limited THEN the System SHALL handle the error gracefully and log the limitation

### Requirement 3: Add FalkorDB Configuration

**User Story:** As a system administrator, I want FalkorDB configuration parameters, so that I can configure the database connection.

#### Acceptance Criteria

1. THE System SHALL include FALKORDB_HOST configuration parameter in config.py with default value "localhost"
2. THE System SHALL include FALKORDB_PORT configuration parameter in config.py with default value 6379
3. THE System SHALL include FALKORDB_USERNAME configuration parameter in config.py as optional
4. THE System SHALL include FALKORDB_PASSWORD configuration parameter in config.py as optional
5. THE System SHALL include FALKORDB_DATABASE configuration parameter in config.py with default value "asta_graph"
6. THE System SHALL include all FalkorDB parameters in .env.template with example values
7. THE System SHALL remove all NEO4J_* parameters from config.py
8. THE System SHALL remove all NEO4J_* parameters from .env.template

### Requirement 4: Update Memory Engine Integration

**User Story:** As a developer, I want the memory engine to use FalkorDB, so that entity operations use the new graph database.

#### Acceptance Criteria

1. WHEN memory_engine.py imports graph layer THEN the System SHALL import from backend.app.services.memory.graph_ltm
2. WHEN memory_engine.py calls get_all_entity_names THEN the System SHALL call graph_ltm.get_all_entity_names()
3. WHEN memory_engine.py calls get_current_focus THEN the System SHALL call graph_ltm.get_current_focus()
4. WHEN memory_engine.py calls get_cluster_session_ids THEN the System SHALL call graph_ltm.get_cluster_session_ids()
5. WHEN memory_engine.py calls upsert_entity THEN the System SHALL call graph_ltm.upsert_entity()
6. WHEN memory_engine.py calls link_session_to_entities THEN the System SHALL call graph_ltm.link_session_to_entities()
7. WHEN memory_engine.py calls update_current_focus THEN the System SHALL call graph_ltm.update_current_focus()
8. THE Memory_Engine SHALL connect graph_ltm during connect_all lifecycle method
9. THE Memory_Engine SHALL disconnect graph_ltm during disconnect_all lifecycle method

### Requirement 5: Update Prefetch Engine Integration

**User Story:** As a developer, I want the prefetch engine to use FalkorDB, so that entity spotting and caching work with the new database.

#### Acceptance Criteria

1. WHEN prefetch_engine.py imports graph layer THEN the System SHALL import from backend.app.services.memory.graph_ltm
2. WHEN prefetch_engine loads known entities THEN the System SHALL call graph_ltm.get_all_entity_names()
3. WHEN prefetch_engine performs cluster search THEN the System SHALL call graph_ltm.get_cluster_session_ids()
4. WHEN prefetch_engine refreshes entities THEN the System SHALL call graph_ltm.get_all_entity_names()

### Requirement 6: Update Database Manager

**User Story:** As a developer, I want database manager to not initialize Neo4j, so that only FalkorDB connections are established.

#### Acceptance Criteria

1. THE System SHALL remove Neo4j driver initialization from database.py connect() method
2. THE System SHALL remove Neo4j import statements from database.py
3. THE System SHALL remove Neo4j health check from database.py ping() method
4. THE System SHALL remove Neo4j disconnect logic from database.py disconnect() method

### Requirement 7: Update Health Check Endpoints

**User Story:** As a system operator, I want health checks to verify FalkorDB, so that I can monitor the graph database connectivity.

#### Acceptance Criteria

1. WHEN health check endpoint is called THEN the System SHALL check FalkorDB connectivity instead of Neo4j
2. THE System SHALL remove Neo4j health check from backend/app/api/health.py deep_health_check()
3. THE System SHALL add FalkorDB health check to backend/app/api/health.py deep_health_check()
4. WHEN FalkorDB is not configured THEN the System SHALL report "not_configured" status
5. WHEN FalkorDB connection fails THEN the System SHALL report "error" status with error message

### Requirement 8: Update Test Files

**User Story:** As a developer, I want test files to verify FalkorDB integration, so that CI/CD can validate the migration.

#### Acceptance Criteria

1. THE System SHALL update all test files that import memory.l2_graph to import backend.app.services.memory.graph_ltm
2. WHEN tests verify L2 layer THEN the System SHALL test graph_ltm.initialize() and connectivity
3. THE System SHALL remove any test files that are specific to Neo4j schema initialization
4. WHEN tests call L2 methods THEN the System SHALL call graph_ltm methods instead of l2_graph methods

### Requirement 9: Document Graphiti Limitations

**User Story:** As a developer, I want known limitations documented, so that I understand the current state of the Graphiti integration.

#### Acceptance Criteria

1. THE System SHALL document that add_episode LLM extraction is disabled due to Gemini API rate limits
2. THE System SHALL document that search operations work with FalkorDB
3. THE System SHALL document that manual entity creation works as a workaround
4. THE System SHALL document that entity relationship operations work with FalkorDB
5. THE documentation SHALL be placed in graph_ltm.py module docstring

### Requirement 10: Maintain Backward Compatibility

**User Story:** As a developer, I want the L2 API to remain consistent, so that calling code doesn't break during migration.

#### Acceptance Criteria

1. THE Graph_LTM SHALL provide the same method signatures as l2_graph.py
2. WHEN existing code calls L2 methods THEN the System SHALL execute without errors after migration
3. THE Graph_LTM SHALL return data in the same format as Neo4j implementation for get_cluster_session_ids()
4. THE Graph_LTM SHALL return data in the same format as Neo4j implementation for get_all_entity_names()
5. THE Graph_LTM SHALL return data in the same format as Neo4j implementation for get_current_focus()

### Requirement 11: Add FalkorDB Dependencies

**User Story:** As a developer, I want FalkorDB and Graphiti dependencies installed, so that the system can connect to the new database.

#### Acceptance Criteria

1. THE System SHALL include falkordb in requirements.txt
2. THE System SHALL include graphiti-core in requirements.txt
3. THE System SHALL specify compatible version ranges for FalkorDB dependencies
4. THE System SHALL remove neo4j from requirements.txt

### Requirement 12: Session-Entity Linking

**User Story:** As a system, I want to link sessions to entities in FalkorDB, so that cluster retrieval can find related conversations.

#### Acceptance Criteria

1. WHEN a session completes THEN the System SHALL create entity nodes in FalkorDB for all extracted entities
2. WHEN a session completes THEN the System SHALL create a session node in FalkorDB
3. WHEN a session completes THEN the System SHALL create edges from session node to all discussed entity nodes
4. WHEN performing cluster retrieval THEN the System SHALL use Graphiti search to find sessions connected to given entities
5. WHEN performing cluster retrieval with depth > 1 THEN the System SHALL traverse entity relationships to find indirectly related sessions

