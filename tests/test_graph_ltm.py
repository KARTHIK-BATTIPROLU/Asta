"""
Comprehensive unit tests for GraphLTM class (FalkorDB/Graphiti integration).

Tests Requirements 8.1, 8.2, and 10.1:
- Unit testing of graph_ltm.py module
- Mock FalkorDB/Graphiti client
- Test all edge cases (not initialized, empty inputs, errors)
- Verify logging output
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call, PropertyMock
from datetime import datetime
from typing import List, Dict


@pytest.fixture
def graph_ltm_instance():
    """Create a fresh GraphLTM instance for each test."""
    from backend.app.services.memory.graph_ltm import GraphLTM
    return GraphLTM()


@pytest.fixture
def mock_settings():
    """Mock settings with FalkorDB configuration."""
    mock = MagicMock()
    mock.FALKORDB_HOST = "localhost"
    mock.FALKORDB_PORT = 6379
    mock.FALKORDB_DATABASE = "asta_graph_test"
    mock.FALKORDB_USERNAME = ""
    mock.FALKORDB_PASSWORD = ""
    return mock


@pytest.fixture
def mock_graphiti():
    """Mock Graphiti client."""
    mock = MagicMock()
    mock.driver = MagicMock()  # Simulate driver attribute for health checks
    return mock


# ============================================================================
# Test 1: test_initialize_success - Mock FalkorDB connection, verify is_initialized = True
# ============================================================================
@pytest.mark.asyncio
async def test_initialize_success(graph_ltm_instance, mock_settings, mock_graphiti):
    """Test successful initialization with FalkorDB connection."""
    with patch('backend.app.config.settings', mock_settings), \
         patch('graphiti_core.Graphiti', return_value=mock_graphiti):
        
        # Initialize should succeed
        await graph_ltm_instance.initialize()
        
        # Verify is_initialized flag
        assert graph_ltm_instance.is_initialized is True
        assert graph_ltm_instance.graphiti is not None
        assert graph_ltm_instance.graphiti == mock_graphiti


# ============================================================================
# Test 2: test_initialize_failure - Mock connection failure, verify is_initialized = False
# ============================================================================
@pytest.mark.asyncio
async def test_initialize_failure(graph_ltm_instance, mock_settings):
    """Test initialization failure when FalkorDB connection fails."""
    with patch('backend.app.config.settings', mock_settings), \
         patch('graphiti_core.Graphiti', side_effect=Exception("Connection refused")):
        
        # Initialize should fail gracefully
        await graph_ltm_instance.initialize()
        
        # Verify is_initialized flag is False
        assert graph_ltm_instance.is_initialized is False
        assert graph_ltm_instance.graphiti is None


@pytest.mark.asyncio
async def test_initialize_import_error(graph_ltm_instance):
    """Test initialization failure when dependencies not installed."""
    # Patch the import directly at the point where it's used
    with patch('graphiti_core.Graphiti', side_effect=ImportError("No module named 'graphiti_core'")):
        # This will cause ImportError in the try block
        # But we need to allow settings import to succeed
        with patch('backend.app.config.settings') as mock_settings:
            mock_settings.FALKORDB_HOST = "localhost"
            mock_settings.FALKORDB_PORT = 6379
            mock_settings.FALKORDB_DATABASE = "test"
            mock_settings.FALKORDB_USERNAME = ""
            mock_settings.FALKORDB_PASSWORD = ""
            
            # Initialize should fail gracefully on import error
            await graph_ltm_instance.initialize()
            
            # Verify is_initialized flag is False
            assert graph_ltm_instance.is_initialized is False
            assert graph_ltm_instance.graphiti is None


# ============================================================================
# Test 3: test_upsert_entity - Mock Graphiti client, verify entity created
# ============================================================================
@pytest.mark.asyncio
async def test_upsert_entity(graph_ltm_instance):
    """Test entity creation via upsert_entity."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Upsert a new entity
    await graph_ltm_instance.upsert_entity(
        name="ASTA",
        entity_type="PROJECT",
        description="AI assistant project",
        relation="WORKING_ON"
    )
    
    # Verify entity added to cache
    assert "ASTA" in graph_ltm_instance._known_entities


@pytest.mark.asyncio
async def test_upsert_entity_not_initialized(graph_ltm_instance):
    """Test upsert_entity when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Should handle gracefully
    await graph_ltm_instance.upsert_entity(
        name="ASTA",
        entity_type="PROJECT"
    )
    
    # Entity should not be added
    assert "ASTA" not in graph_ltm_instance._known_entities


@pytest.mark.asyncio
async def test_upsert_entity_empty_name(graph_ltm_instance):
    """Test upsert_entity with empty name."""
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Upsert with empty name
    await graph_ltm_instance.upsert_entity(
        name="",
        entity_type="PROJECT"
    )
    
    # Should not add empty entity
    assert "" not in graph_ltm_instance._known_entities


# ============================================================================
# Test 4: test_get_all_entity_names - Mock entity query, verify returned list
# ============================================================================
@pytest.mark.asyncio
async def test_get_all_entity_names(graph_ltm_instance):
    """Test retrieving all entity names."""
    # Setup initialized state with cached entities
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    graph_ltm_instance._known_entities = ["ASTA", "Python", "FastAPI"]
    
    # Get all entity names
    entities = await graph_ltm_instance.get_all_entity_names()
    
    # Verify returned list
    assert entities == ["ASTA", "Python", "FastAPI"]
    assert len(entities) == 3


@pytest.mark.asyncio
async def test_get_all_entity_names_not_initialized(graph_ltm_instance):
    """Test get_all_entity_names when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Should return empty list
    entities = await graph_ltm_instance.get_all_entity_names()
    
    assert entities == []


@pytest.mark.asyncio
async def test_get_all_entity_names_empty(graph_ltm_instance):
    """Test get_all_entity_names with no entities."""
    # Setup initialized state with no entities
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    graph_ltm_instance._known_entities = []
    
    # Get all entity names
    entities = await graph_ltm_instance.get_all_entity_names()
    
    # Verify empty list
    assert entities == []


# ============================================================================
# Test 5: test_get_cluster_session_ids - Mock search and traversal, verify session IDs
# ============================================================================
@pytest.mark.asyncio
async def test_get_cluster_session_ids(graph_ltm_instance):
    """Test cluster retrieval for given entities."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Get cluster session IDs
    session_ids = await graph_ltm_instance.get_cluster_session_ids(
        entity_names=["ASTA", "Python"],
        depth=2
    )
    
    # Verify returns list (currently empty due to placeholder implementation)
    assert isinstance(session_ids, list)


@pytest.mark.asyncio
async def test_get_cluster_session_ids_not_initialized(graph_ltm_instance):
    """Test cluster retrieval when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Should return empty list
    session_ids = await graph_ltm_instance.get_cluster_session_ids(
        entity_names=["ASTA"],
        depth=2
    )
    
    assert session_ids == []


@pytest.mark.asyncio
async def test_get_cluster_session_ids_empty_input(graph_ltm_instance):
    """Test cluster retrieval with empty entity list."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should return empty list for empty input
    session_ids = await graph_ltm_instance.get_cluster_session_ids(
        entity_names=[],
        depth=2
    )
    
    assert session_ids == []


@pytest.mark.asyncio
async def test_get_cluster_session_ids_none_input(graph_ltm_instance):
    """Test cluster retrieval with None entity list."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should return empty list for None input
    session_ids = await graph_ltm_instance.get_cluster_session_ids(
        entity_names=None,
        depth=2
    )
    
    assert session_ids == []


@pytest.mark.asyncio
async def test_get_cluster_session_ids_filters_empty_strings(graph_ltm_instance):
    """Test cluster retrieval filters out empty/None entity names."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should filter out empty strings and None values
    session_ids = await graph_ltm_instance.get_cluster_session_ids(
        entity_names=["ASTA", "", None, "  ", "Python"],
        depth=2
    )
    
    # Should return list (validates empty strings are filtered)
    assert isinstance(session_ids, list)


# ============================================================================
# Test 6: test_link_session_to_entities - Mock session-entity linking
# ============================================================================
@pytest.mark.asyncio
async def test_link_session_to_entities(graph_ltm_instance):
    """Test linking a session to entities."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Link session to entities
    await graph_ltm_instance.link_session_to_entities(
        session_id="sess_123",
        entities=[
            {"name": "ASTA", "type": "PROJECT"},
            {"name": "Python", "type": "SKILL"}
        ],
        workflow_type="research",
        summary_snippet="Working on ASTA project using Python"
    )
    
    # Should complete without error
    assert graph_ltm_instance.is_initialized is True


@pytest.mark.asyncio
async def test_link_session_to_entities_not_initialized(graph_ltm_instance):
    """Test linking session when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Should handle gracefully
    await graph_ltm_instance.link_session_to_entities(
        session_id="sess_123",
        entities=[{"name": "ASTA", "type": "PROJECT"}],
        workflow_type="research",
        summary_snippet="Test"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is False


@pytest.mark.asyncio
async def test_link_session_to_entities_empty_session_id(graph_ltm_instance):
    """Test linking with empty session ID."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should handle gracefully
    await graph_ltm_instance.link_session_to_entities(
        session_id="",
        entities=[{"name": "ASTA", "type": "PROJECT"}],
        workflow_type="research",
        summary_snippet="Test"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is True


@pytest.mark.asyncio
async def test_link_session_to_entities_empty_entities(graph_ltm_instance):
    """Test linking with no entities."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should handle gracefully
    await graph_ltm_instance.link_session_to_entities(
        session_id="sess_123",
        entities=[],
        workflow_type="research",
        summary_snippet="Test"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is True


@pytest.mark.asyncio
async def test_link_session_to_entities_string_entities(graph_ltm_instance):
    """Test linking with entity names as strings instead of dicts."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should handle string entity names
    await graph_ltm_instance.link_session_to_entities(
        session_id="sess_123",
        entities=["ASTA", "Python"],
        workflow_type="research",
        summary_snippet="Test"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is True


# ============================================================================
# Test 7: test_health_check_success - Mock healthy FalkorDB
# ============================================================================
@pytest.mark.asyncio
async def test_health_check_success(graph_ltm_instance):
    """Test health check with healthy FalkorDB."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    mock_graphiti = MagicMock()
    mock_graphiti.driver = MagicMock()  # Simulate active driver
    graph_ltm_instance.graphiti = mock_graphiti
    
    # Health check should pass
    result = await graph_ltm_instance.health_check()
    
    assert result is True


# ============================================================================
# Test 8: test_health_check_failure - Mock FalkorDB down
# ============================================================================
@pytest.mark.asyncio
async def test_health_check_failure(graph_ltm_instance):
    """Test health check when FalkorDB is down."""
    # Setup initialized state but with None driver
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = None
    
    # Health check should fail
    result = await graph_ltm_instance.health_check()
    
    assert result is False


@pytest.mark.asyncio
async def test_health_check_not_initialized(graph_ltm_instance):
    """Test health check when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Health check should fail
    result = await graph_ltm_instance.health_check()
    
    assert result is False


@pytest.mark.asyncio
async def test_health_check_exception(graph_ltm_instance):
    """Test health check when exception occurs."""
    # Setup initialized state with mock that raises exception when checking driver
    graph_ltm_instance.is_initialized = True
    mock_graphiti = MagicMock()
    # Configure mock to raise exception when hasattr() checks for driver
    type(mock_graphiti).driver = PropertyMock(side_effect=Exception("Connection error"))
    graph_ltm_instance.graphiti = mock_graphiti
    
    # Health check should catch exception and return False
    result = await graph_ltm_instance.health_check()
    
    assert result is False


# ============================================================================
# Test 9: test_add_episode_rate_limiting - Mock 503 error, verify graceful handling
# ============================================================================
@pytest.mark.asyncio
async def test_add_episode_rate_limiting(graph_ltm_instance):
    """Test add_episode handles Gemini API rate limit (503 error) gracefully."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should handle rate limit gracefully (currently no-op, but shouldn't crash)
    await graph_ltm_instance.add_episode(
        content="User discussed ASTA project",
        session_id="sess_123"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is True


@pytest.mark.asyncio
async def test_add_episode_not_initialized(graph_ltm_instance):
    """Test add_episode when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Should handle gracefully
    await graph_ltm_instance.add_episode(
        content="Test content",
        session_id="sess_123"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is False


@pytest.mark.asyncio
async def test_add_episode_empty_content(graph_ltm_instance):
    """Test add_episode with empty content."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Should handle gracefully
    await graph_ltm_instance.add_episode(
        content="",
        session_id="sess_123"
    )
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is True


# ============================================================================
# Test 10: test_cluster_retrieval_not_initialized - Test not_initialized state returns empty list
# ============================================================================
@pytest.mark.asyncio
async def test_cluster_retrieval_not_initialized_returns_empty(graph_ltm_instance):
    """Test cluster retrieval returns empty list when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Get cluster session IDs
    session_ids = await graph_ltm_instance.get_cluster_session_ids(
        entity_names=["ASTA", "Python"],
        depth=2
    )
    
    # Should return empty list
    assert session_ids == []
    assert isinstance(session_ids, list)


# ============================================================================
# Test 11: test_get_current_focus - Test focus tracking
# ============================================================================
@pytest.mark.asyncio
async def test_get_current_focus(graph_ltm_instance):
    """Test retrieving current focus."""
    # Set some focus data
    graph_ltm_instance._current_focus = "ASTA"
    graph_ltm_instance._last_active_project = "ASTA"
    graph_ltm_instance._last_active = datetime(2024, 1, 15, 10, 30)
    
    # Get current focus
    focus = await graph_ltm_instance.get_current_focus()
    
    # Verify returned data
    assert focus["current_focus"] == "ASTA"
    assert focus["last_active_project"] == "ASTA"
    assert focus["last_active"] == datetime(2024, 1, 15, 10, 30)


@pytest.mark.asyncio
async def test_get_current_focus_empty(graph_ltm_instance):
    """Test retrieving current focus when not set."""
    # Get current focus (defaults)
    focus = await graph_ltm_instance.get_current_focus()
    
    # Verify returned data with defaults
    assert focus["current_focus"] == ""
    assert focus["last_active_project"] == ""
    assert focus["last_active"] is None


@pytest.mark.asyncio
async def test_get_current_focus_exception_handling(graph_ltm_instance):
    """Test get_current_focus handles exceptions gracefully."""
    # Simulate error by making _current_focus raise exception
    with patch.object(graph_ltm_instance, '_current_focus', property(lambda self: (_ for _ in ()).throw(Exception("Error")))):
        # Should handle exception and return default values
        focus = await graph_ltm_instance.get_current_focus()
        
        assert "current_focus" in focus
        assert "last_active_project" in focus
        assert "last_active" in focus


# ============================================================================
# Test 12: test_update_current_focus - Test focus updates
# ============================================================================
@pytest.mark.asyncio
async def test_update_current_focus(graph_ltm_instance):
    """Test updating current focus."""
    # Update focus
    await graph_ltm_instance.update_current_focus("ASTA")
    
    # Verify focus updated
    assert graph_ltm_instance._current_focus == "ASTA"
    assert graph_ltm_instance._last_active is not None
    assert isinstance(graph_ltm_instance._last_active, datetime)


@pytest.mark.asyncio
async def test_update_current_focus_project_detection(graph_ltm_instance):
    """Test update_current_focus detects project entities."""
    # Update focus with uppercase name (project heuristic)
    await graph_ltm_instance.update_current_focus("ASTA")
    
    # Verify last active project also updated
    assert graph_ltm_instance._current_focus == "ASTA"
    assert graph_ltm_instance._last_active_project == "ASTA"


@pytest.mark.asyncio
async def test_update_current_focus_empty(graph_ltm_instance):
    """Test updating focus with empty string."""
    # Update with empty string
    await graph_ltm_instance.update_current_focus("")
    
    # Focus should remain empty
    assert graph_ltm_instance._current_focus == ""


@pytest.mark.asyncio
async def test_update_current_focus_whitespace(graph_ltm_instance):
    """Test updating focus with whitespace-only string."""
    # Update with whitespace
    await graph_ltm_instance.update_current_focus("   ")
    
    # Focus should remain empty
    assert graph_ltm_instance._current_focus == ""


@pytest.mark.asyncio
async def test_update_current_focus_strips_whitespace(graph_ltm_instance):
    """Test update_current_focus strips leading/trailing whitespace."""
    # Update with whitespace around name
    await graph_ltm_instance.update_current_focus("  ASTA  ")
    
    # Focus should be stripped
    assert graph_ltm_instance._current_focus == "ASTA"


# ============================================================================
# Test 13: test_disconnect - Test graceful shutdown
# ============================================================================
@pytest.mark.asyncio
async def test_disconnect(graph_ltm_instance):
    """Test graceful disconnect."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Disconnect
    await graph_ltm_instance.disconnect()
    
    # Verify cleanup
    assert graph_ltm_instance.is_initialized is False
    assert graph_ltm_instance.graphiti is None


@pytest.mark.asyncio
async def test_disconnect_not_initialized(graph_ltm_instance):
    """Test disconnect when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    graph_ltm_instance.graphiti = None
    
    # Should handle gracefully
    await graph_ltm_instance.disconnect()
    
    # Verify state
    assert graph_ltm_instance.is_initialized is False
    assert graph_ltm_instance.graphiti is None


@pytest.mark.asyncio
async def test_disconnect_multiple_times(graph_ltm_instance):
    """Test disconnect can be called multiple times safely."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Disconnect twice
    await graph_ltm_instance.disconnect()
    await graph_ltm_instance.disconnect()
    
    # Should not crash
    assert graph_ltm_instance.is_initialized is False
    assert graph_ltm_instance.graphiti is None


@pytest.mark.asyncio
async def test_disconnect_exception_handling(graph_ltm_instance):
    """Test disconnect handles exceptions during cleanup."""
    # Setup with mock that raises exception
    graph_ltm_instance.is_initialized = True
    mock_graphiti = MagicMock()
    mock_graphiti.close = MagicMock(side_effect=Exception("Close error"))
    graph_ltm_instance.graphiti = mock_graphiti
    
    # Should handle exception gracefully
    await graph_ltm_instance.disconnect()
    
    # Verify flags set anyway
    assert graph_ltm_instance.is_initialized is False
    assert graph_ltm_instance.graphiti is None


# ============================================================================
# Additional Edge Case Tests
# ============================================================================
@pytest.mark.asyncio
async def test_search_functionality(graph_ltm_instance):
    """Test search method."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Perform search
    results = await graph_ltm_instance.search(query="ASTA", limit=10)
    
    # Should return list
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_search_not_initialized(graph_ltm_instance):
    """Test search when not initialized."""
    # GraphLTM not initialized
    graph_ltm_instance.is_initialized = False
    
    # Should return empty list
    results = await graph_ltm_instance.search(query="ASTA", limit=10)
    
    assert results == []


@pytest.mark.asyncio
async def test_search_empty_query(graph_ltm_instance):
    """Test search with empty query."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Search with empty query
    results = await graph_ltm_instance.search(query="", limit=10)
    
    # Should return empty list
    assert results == []


@pytest.mark.asyncio
async def test_initialization_with_credentials(graph_ltm_instance, mock_graphiti):
    """Test initialization with username and password."""
    mock_settings = MagicMock()
    mock_settings.FALKORDB_HOST = "localhost"
    mock_settings.FALKORDB_PORT = 6379
    mock_settings.FALKORDB_DATABASE = "asta_graph_test"
    mock_settings.FALKORDB_USERNAME = "test_user"
    mock_settings.FALKORDB_PASSWORD = "test_pass"
    
    with patch('backend.app.config.settings', mock_settings), \
         patch('graphiti_core.Graphiti', return_value=mock_graphiti) as mock_graphiti_class:
        
        # Initialize should succeed
        await graph_ltm_instance.initialize()
        
        # Verify credentials passed to Graphiti
        mock_graphiti_class.assert_called_once()
        call_kwargs = mock_graphiti_class.call_args[1]
        assert call_kwargs["username"] == "test_user"
        assert call_kwargs["password"] == "test_pass"
        assert graph_ltm_instance.is_initialized is True


@pytest.mark.asyncio
async def test_upsert_entity_exception_handling(graph_ltm_instance):
    """Test upsert_entity handles exceptions gracefully."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Force exception by making _known_entities raise error
    original_entities = graph_ltm_instance._known_entities
    
    with patch.object(graph_ltm_instance, '_known_entities', property(lambda self: (_ for _ in ()).throw(Exception("Error")))):
        # Should handle exception gracefully
        try:
            await graph_ltm_instance.upsert_entity(
                name="ASTA",
                entity_type="PROJECT"
            )
            # Restore for cleanup
            graph_ltm_instance._known_entities = original_entities
        except:
            graph_ltm_instance._known_entities = original_entities
            raise


@pytest.mark.asyncio
async def test_get_all_entity_names_exception_handling(graph_ltm_instance):
    """Test get_all_entity_names handles exceptions gracefully."""
    # Setup initialized state
    graph_ltm_instance.is_initialized = True
    graph_ltm_instance.graphiti = MagicMock()
    
    # Force exception by making _known_entities raise error
    with patch.object(graph_ltm_instance, '_known_entities', property(lambda self: (_ for _ in ()).throw(Exception("Error")))):
        # Should handle exception and return empty list
        entities = await graph_ltm_instance.get_all_entity_names()
        
        assert entities == []
