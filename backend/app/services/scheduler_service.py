"""
ASTA Scheduler Service
Handles scheduled tasks like morning alarms and night planning.
"""
import logging
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for scheduling recurring and one-time tasks."""
    
    def __init__(self):
        """Initialize scheduler."""
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self._alarm_callback = None
        self._night_callback = None
    
    def set_alarm_callback(self, coro_func):
        """Set callback for morning alarm."""
        self._alarm_callback = coro_func
    
    def set_night_callback(self, coro_func):
        """Set callback for night planning."""
        self._night_callback = coro_func
    
    def start(self):
        """Start the scheduler with default jobs."""
        # Morning alarm: 5:30 AM IST every day
        self.scheduler.add_job(
            self._trigger_morning_alarm,
            CronTrigger(hour=5, minute=30, timezone="Asia/Kolkata"),
            id="morning_alarm",
            replace_existing=True
        )
        # Night planning: 10:30 PM IST every day
        self.scheduler.add_job(
            self._trigger_night_planning,
            CronTrigger(hour=22, minute=30, timezone="Asia/Kolkata"),
            id="night_planning",
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(
            "Scheduler started: morning alarm 5:30 AM IST, "
            "night planning 10:30 PM IST"
        )
    
    async def _trigger_morning_alarm(self):
        """Trigger morning alarm callback."""
        logger.info("SCHEDULER: Morning alarm triggered")
        if self._alarm_callback:
            asyncio.create_task(self._alarm_callback())
    
    async def _trigger_night_planning(self):
        """Trigger night planning callback."""
        logger.info("SCHEDULER: Night planning triggered")
        if self._night_callback:
            asyncio.create_task(self._night_callback())
    
    def add_one_time_reminder(
        self,
        reminder_id: str,
        run_at: datetime,
        callback
    ) -> bool:
        """Add a one-time reminder. Returns success status."""
        try:
            self.scheduler.add_job(
                callback,
                DateTrigger(run_date=run_at),
                id=reminder_id,
                replace_existing=True
            )
            logger.info(f"Reminder scheduled: {reminder_id} at {run_at}")
            return True
        except Exception as e:
            logger.error(f"Failed to schedule reminder {reminder_id}: {e}")
            return False
    
    def remove_reminder(self, reminder_id: str):
        """Remove a scheduled reminder."""
        try:
            self.scheduler.remove_job(reminder_id)
            logger.info(f"Removed reminder: {reminder_id}")
        except Exception as e:
            logger.warning(f"Failed to remove reminder {reminder_id}: {e}")
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")


# Global instance
scheduler_service = SchedulerService()
