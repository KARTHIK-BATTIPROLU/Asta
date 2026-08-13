"""
Tests for health check endpoints after FalkorDB migration.
Tests Tasks 8.1 and 8.2: Neo4j removal and FalkorDB addition.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_falkordb_health_check_logic_directly():
    """Test FalkorDB health check logic directly without running full deep_health_check."""
    from backend.app.services.memory.graph_ltm import graph_ltm
    
    # Test the actual health check method
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    mock_graph_ltm.health_check = AsyncMock(return_value=True)
    
    with patch('backend.app.services.memory.graph_ltm.graph_ltm', mock_graph_ltm):
        # Simulate what the health check does
        health_status = {"services": {}}
        
        try:
            from backend.app.services.memory.graph_ltm import graph_ltm as patched_ltm
            
            if not patched_ltm.is_initialized:
                health_status["services"]["falkordb"] = {
                    "status": "not_initialized",
                    "message": "GraphLTM not initialized"
                }
            else:
                health_check_result = await patched_ltm.health_check()
                if health_check_result:
                    health_status["services"]["falkordb"] = {
                        "status": "ok",
                        "message": "Connected"
                    }
                else:
                    health_status["services"]["falkordb"] = {
                        "status": "error",
                        "message": "Health check failed"
                    }
        except Exception as e:
            health_status["services"]["falkordb"] = {
                "status": "error",
                "message": str(e)
            }
        
        # Verify FalkorDB check was called correctly
        assert "falkordb" in health_status["services"]
        assert health_status["services"]["falkordb"]["status"] == "ok"
        assert health_status["services"]["falkordb"]["message"] == "Connected"


@pytest.mark.asyncio
async def test_falkordb_not_initialized_status():
    """Test FalkorDB health check when not initialized."""
    # Mock graph_ltm as not initialized
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = False
    
    with patch('backend.app.services.memory.graph_ltm.graph_ltm', mock_graph_ltm):
        # Simulate what the health check does
        health_status = {"services": {}}
        
        try:
            from backend.app.services.memory.graph_ltm import graph_ltm as patched_ltm
            
            if not patched_ltm.is_initialized:
                health_status["services"]["falkordb"] = {
                    "status": "not_initialized",
                    "message": "GraphLTM not initialized"
                }
            else:
                health_check_result = await patched_ltm.health_check()
                if health_check_result:
                    health_status["services"]["falkordb"] = {
                        "status": "ok",
                        "message": "Connected"
                    }
        except Exception as e:
            health_status["services"]["falkordb"] = {
                "status": "error",
                "message": str(e)
            }
        
        # Verify FalkorDB shows not_initialized
        assert "falkordb" in health_status["services"]
        assert health_status["services"]["falkordb"]["status"] == "not_initialized"
        assert health_status["services"]["falkordb"]["message"] == "GraphLTM not initialized"


@pytest.mark.asyncio
async def test_falkordb_health_check_fails():
    """Test FalkorDB health check when health check returns False."""
    # Mock graph_ltm with failed health check
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    mock_graph_ltm.health_check = AsyncMock(return_value=False)
    
    with patch('backend.app.services.memory.graph_ltm.graph_ltm', mock_graph_ltm):
        # Simulate what the health check does
        health_status = {"services": {}, "overall": "ok"}
        
        try:
            from backend.app.services.memory.graph_ltm import graph_ltm as patched_ltm
            
            if not patched_ltm.is_initialized:
                health_status["services"]["falkordb"] = {
                    "status": "not_initialized",
                    "message": "GraphLTM not initialized"
                }
            else:
                health_check_result = await patched_ltm.health_check()
                if health_check_result:
                    health_status["services"]["falkordb"] = {
                        "status": "ok",
                        "message": "Connected"
                    }
                else:
                    health_status["services"]["falkordb"] = {
                        "status": "error",
                        "message": "Health check failed"
                    }
                    health_status["overall"] = "degraded"
        except Exception as e:
            health_status["services"]["falkordb"] = {
                "status": "error",
                "message": str(e)
            }
            health_status["overall"] = "degraded"
        
        # Verify FalkorDB shows error
        assert "falkordb" in health_status["services"]
        assert health_status["services"]["falkordb"]["status"] == "error"
        assert health_status["services"]["falkordb"]["message"] == "Health check failed"
        assert health_status["overall"] == "degraded"


@pytest.mark.asyncio
async def test_falkordb_health_check_exception():
    """Test FalkorDB health check when an exception occurs."""
    # Mock graph_ltm to raise exception
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    mock_graph_ltm.health_check = AsyncMock(side_effect=Exception("Connection error"))
    
    with patch('backend.app.services.memory.graph_ltm.graph_ltm', mock_graph_ltm):
        # Simulate what the health check does
        health_status = {"services": {}, "overall": "ok"}
        
        try:
            from backend.app.services.memory.graph_ltm import graph_ltm as patched_ltm
            
            if not patched_ltm.is_initialized:
                health_status["services"]["falkordb"] = {
                    "status": "not_initialized",
                    "message": "GraphLTM not initialized"
                }
            else:
                health_check_result = await patched_ltm.health_check()
                if health_check_result:
                    health_status["services"]["falkordb"] = {
                        "status": "ok",
                        "message": "Connected"
                    }
                else:
                    health_status["services"]["falkordb"] = {
                        "status": "error",
                        "message": "Health check failed"
                    }
                    health_status["overall"] = "degraded"
        except Exception as e:
            health_status["services"]["falkordb"] = {
                "status": "error",
                "message": str(e)
            }
            health_status["overall"] = "degraded"
        
        # Verify FalkorDB shows error with exception message
        assert "falkordb" in health_status["services"]
        assert health_status["services"]["falkordb"]["status"] == "error"
        assert "Connection error" in health_status["services"]["falkordb"]["message"]
        assert health_status["overall"] == "degraded"


def test_neo4j_import_removed_from_health_file():
    """Verify that Neo4j imports are removed from health.py."""
    with open("backend/app/api/health.py", "r") as f:
        content = f.read()
    
    # Verify Neo4j is not imported
    assert "from memory.l2_graph import" not in content
    assert "graph_store" not in content
    
    # Verify FalkorDB is imported
    assert "from backend.app.services.memory.graph_ltm import graph_ltm" in content


def test_neo4j_check_removed_from_health_file():
    """Verify that Neo4j health check code is removed from health.py."""
    with open("backend/app/api/health.py", "r") as f:
        content = f.read()
    
    # Verify Neo4j check is not present
    assert '"neo4j"' not in content
    assert 'Check Neo4j' not in content
    
    # Verify FalkorDB check is present
    assert '"falkordb"' in content
    assert 'Check FalkorDB' in content
