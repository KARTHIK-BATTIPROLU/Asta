"""Integration tests for updated health endpoint with GraphLTM status."""
import pytest
import time
from unittest.mock import patch, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_health_endpoint_with_graph_ltm_initialized():
    """Test health endpoint returns 'healthy' when GraphLTM is initialized."""
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    
    with patch('backend.app.api.health.graph_ltm', mock_graph_ltm):
        from backend.app.api.health import health_check
        
        response = await health_check()
        
        # Verify response structure (Requirement 9.4)
        assert response["status"] == "healthy"
        assert response["graph_ltm_initialized"] is True
        assert "timestamp" in response
        
        # Verify ISO 8601 format with timezone
        parsed_time = datetime.fromisoformat(response["timestamp"])
        assert parsed_time.tzinfo is not None


@pytest.mark.asyncio
async def test_health_endpoint_with_graph_ltm_not_initialized():
    """Test health endpoint returns 'degraded' when GraphLTM is not initialized."""
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = False
    
    with patch('backend.app.api.health.graph_ltm', mock_graph_ltm):
        from backend.app.api.health import health_check
        
        response = await health_check()
        
        # Verify response structure (Requirement 9.4)
        assert response["status"] == "degraded"
        assert response["graph_ltm_initialized"] is False
        assert "timestamp" in response
        
        # Verify ISO 8601 format with timezone
        parsed_time = datetime.fromisoformat(response["timestamp"])
        assert parsed_time.tzinfo is not None


@pytest.mark.asyncio
async def test_health_endpoint_response_time():
    """Test health endpoint responds within 500ms (Requirement 9.5)."""
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    
    with patch('backend.app.api.health.graph_ltm', mock_graph_ltm):
        from backend.app.api.health import health_check
        
        start_time = time.perf_counter()
        response = await health_check()
        end_time = time.perf_counter()
        
        response_time_ms = (end_time - start_time) * 1000
        
        # Verify response time is under 500ms (Requirement 9.5)
        assert response_time_ms < 500, f"Response time {response_time_ms}ms exceeds 500ms limit"
        
        # Verify response is still valid
        assert "status" in response
        assert "graph_ltm_initialized" in response
        assert "timestamp" in response


@pytest.mark.asyncio
async def test_health_endpoint_response_format():
    """Test health endpoint response contains all required fields with correct types."""
    mock_graph_ltm = MagicMock()
    mock_graph_ltm.is_initialized = True
    
    with patch('backend.app.api.health.graph_ltm', mock_graph_ltm):
        from backend.app.api.health import health_check
        
        response = await health_check()
        
        # Verify all required fields are present
        assert "status" in response
        assert "graph_ltm_initialized" in response
        assert "timestamp" in response
        
        # Verify types
        assert isinstance(response["status"], str)
        assert response["status"] in ["healthy", "degraded"]
        assert isinstance(response["graph_ltm_initialized"], bool)
        assert isinstance(response["timestamp"], str)
        
        # Verify timestamp format (should parse without error)
        datetime.fromisoformat(response["timestamp"])
