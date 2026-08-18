"""Simple test to verify health endpoint update."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_health_check_returns_healthy_when_initialized():
    """Test health endpoint returns 'healthy' when GraphLTM is initialized."""
    # Mock graph_ltm before importing
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    
    with patch.dict('sys.modules', {
        'backend.app.services.memory.graph_ltm': MagicMock(graph_ltm=mock_graph_ltm)
    }):
        with patch('backend.app.api.health.graph_ltm', mock_graph_ltm):
            from backend.app.api.health import health_check
            
            response = await health_check()
            
            assert response["status"] == "healthy"
            assert response["graph_ltm_initialized"] is True
            assert "timestamp" in response
            # Verify timestamp is valid ISO 8601
            datetime.fromisoformat(response["timestamp"])


@pytest.mark.asyncio
async def test_health_check_returns_degraded_when_not_initialized():
    """Test health endpoint returns 'degraded' when GraphLTM is not initialized."""
    # Mock graph_ltm before importing
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = False
    
    with patch('backend.app.api.health.graph_ltm', mock_graph_ltm):
        from backend.app.api.health import health_check
        
        response = await health_check()
        
        assert response["status"] == "degraded"
        assert response["graph_ltm_initialized"] is False
        assert "timestamp" in response
        # Verify timestamp is valid ISO 8601
        datetime.fromisoformat(response["timestamp"])
