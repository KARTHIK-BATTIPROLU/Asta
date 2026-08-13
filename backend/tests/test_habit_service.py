import pytest
import asyncio
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Mock ws_transport so we don't load pipecat and its dependencies
sys.modules["backend.app.api.ws_transport"] = MagicMock()

from backend.app.services.habit_service import habit_service

@pytest.fixture
def mock_db_manager():
    with patch("backend.app.services.habit_service.db_manager") as mock_db:
        yield mock_db

@pytest.fixture
def mock_reminder_service():
    with patch("backend.app.services.habit_service.reminder_service") as mock_rem:
        yield mock_rem

@pytest.mark.asyncio
async def test_habit_escalation(mock_db_manager, mock_reminder_service):
    # Setup mock habits cursor
    mock_habits = MagicMock()
    mock_db_manager.db = {"habits": mock_habits}
    
    # We yield two habits: one at level 0, one at level 3
    async def mock_cursor():
        yield {"_id": "h1", "name": "Jogging", "escalation": 0}
        yield {"_id": "h2", "name": "Reading", "escalation": 3}
        
    class AsyncIterable:
        def __init__(self, data):
            self.data = data
        async def __aiter__(self):
            for item in self.data:
                yield item

    mock_habits.find.return_value = AsyncIterable([
        {"_id": "h1", "name": "Jogging", "escalation": 0},
        {"_id": "h2", "name": "Reading", "escalation": 3}
    ])
    
    # Mock update_one and schedule_reminder as AsyncMocks
    mock_habits.update_one = AsyncMock()
    mock_reminder_service.schedule_reminder = AsyncMock()
    
    await habit_service.run_tick()
    
    # Verify reminder service was called for both since they are unverified
    assert mock_reminder_service.schedule_reminder.call_count == 2
    
    # Verify the updates
    assert mock_habits.update_one.call_count == 2
    
    # H1 goes to level 1
    args_h1, _ = mock_habits.update_one.call_args_list[0]
    assert args_h1[1]["$set"]["escalation"] == 1
    
    # H2 stays at level 3 (cap)
    args_h2, _ = mock_habits.update_one.call_args_list[1]
    assert args_h2[1]["$set"]["escalation"] == 3
