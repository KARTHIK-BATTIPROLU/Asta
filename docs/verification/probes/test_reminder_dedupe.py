import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from pymongo.errors import DuplicateKeyError

from backend.app.services.reminder_service import ReminderService

@pytest.mark.asyncio
async def test_reminder_dedupe():
    # Verify that a duplicate reminder fails to schedule
    service = ReminderService()
    due_ts = datetime.now(timezone.utc)
    
    with patch("backend.app.services.reminder_service.db_manager") as mock_db:
        mock_reminders = AsyncMock()
        mock_db.db.__getitem__.return_value = mock_reminders
        
        # Simulate a DuplicateKeyError from MongoDB
        mock_reminders.insert_one.side_effect = DuplicateKeyError("Duplicate key")
        
        with patch("backend.app.services.reminder_service.scheduler_service") as mock_scheduler:
            # Try to schedule the reminder
            reminder_id = await service.schedule_reminder("Buy milk", due_ts)
            
            # Should return empty string on duplicate error
            assert reminder_id == ""
            
            # Should NOT add to APScheduler
            mock_scheduler.add_one_time_reminder.assert_not_called()
