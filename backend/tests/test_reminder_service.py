import pytest
import asyncio
from datetime import datetime, timezone, timedelta
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Mock ws_transport so we don't load pipecat and its dependencies in this simple test
sys.modules["backend.app.api.ws_transport"] = MagicMock()

from backend.app.services.reminder_service import reminder_service

@pytest.fixture
def mock_db_manager():
    with patch("backend.app.services.reminder_service.db_manager") as mock_db:
        yield mock_db

@pytest.fixture
def mock_scheduler():
    with patch("backend.app.services.reminder_service.scheduler_service") as mock_sched:
        yield mock_sched

@pytest.mark.asyncio
async def test_schedule_reminder(mock_db_manager, mock_scheduler):
    mock_reminders = AsyncMock()
    mock_db_manager.db = {"reminders": mock_reminders}
    
    mock_insert_result = MagicMock()
    mock_insert_result.inserted_id = "test_id"
    mock_reminders.insert_one.return_value = mock_insert_result
    
    due_ts = datetime.now(timezone.utc) + timedelta(hours=1)
    reminder_id = await reminder_service.schedule_reminder("Call mom", due_ts)
    
    assert reminder_id == "test_id"
    mock_reminders.insert_one.assert_called_once()
    mock_scheduler.add_one_time_reminder.assert_called_once_with(
        reminder_id="test_id",
        run_at=due_ts,
        callback=reminder_service.trigger_reminder,
        args=["test_id"]
    )

@pytest.mark.asyncio
async def test_trigger_reminder_max_retries(mock_db_manager):
    mock_reminders = AsyncMock()
    mock_db_manager.db = {"reminders": mock_reminders}
    mock_db_manager.ObjectId = lambda x: x
    
    mock_reminders.find_one.return_value = {
        "_id": "test_id",
        "state": "awaiting_ack",
        "attempts": 3,
        "text": "Call mom"
    }
    
    await reminder_service.trigger_reminder("test_id")
    
    # Assert parked state
    mock_reminders.update_one.assert_called_once()
    args, _ = mock_reminders.update_one.call_args
    assert args[1]["$set"]["state"] == "parked"

@pytest.mark.asyncio
async def test_ack_reminder(mock_db_manager):
    mock_reminders = AsyncMock()
    mock_db_manager.db = {"reminders": mock_reminders}
    mock_db_manager.ObjectId = lambda x: x
    
    mock_update_result = MagicMock()
    mock_update_result.modified_count = 1
    mock_reminders.update_one.return_value = mock_update_result
    
    success = await reminder_service.ack_reminder("test_id", "voice")
    
    assert success is True
    mock_reminders.update_one.assert_called_once()
    args, _ = mock_reminders.update_one.call_args
    assert args[1]["$set"]["state"] == "acked"
    assert args[1]["$set"]["ack_method"] == "voice"
