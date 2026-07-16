import pytest
from unittest.mock import patch, AsyncMock

# Mock db_manager early
import sys
sys.modules["backend.app.db.database"] = AsyncMock()

from backend.app.api.sync_routes import sync_offline_items, SyncRequest, SyncItem

@pytest.fixture
def mock_db_manager():
    with patch("backend.app.api.sync_routes.db_manager") as mock:
        yield mock

@pytest.mark.asyncio
async def test_offline_sync_capture(mock_db_manager):
    mock_db_manager.db.offline_sync.find_one = AsyncMock(return_value=None)
    mock_db_manager.db.memories.insert_one = AsyncMock()
    mock_db_manager.db.offline_sync.insert_one = AsyncMock()

    req = SyncRequest(items=[
        SyncItem(
            client_id="client-123",
            kind="capture",
            payload={"text": "offline thought"},
            created_ts=1234567890
        )
    ])

    response = await sync_offline_items(req)
    
    assert len(response["results"]) == 1
    assert response["results"][0]["status"] == "success"
    
    mock_db_manager.db.memories.insert_one.assert_called_once()
    mock_db_manager.db.offline_sync.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_offline_sync_idempotency(mock_db_manager):
    # Simulate already synced
    mock_db_manager.db.offline_sync.find_one = AsyncMock(return_value={"_id": "exists"})
    mock_db_manager.db.memories.insert_one = AsyncMock()

    req = SyncRequest(items=[
        SyncItem(
            client_id="client-123",
            kind="capture",
            payload={"text": "offline thought"},
            created_ts=1234567890
        )
    ])

    response = await sync_offline_items(req)
    
    assert response["results"][0]["status"] == "ignored"
    mock_db_manager.db.memories.insert_one.assert_not_called()
