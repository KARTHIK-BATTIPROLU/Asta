"""
ASTA Scheduler Service
Handles scheduled tasks like morning alarms and night planning.
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.mongodb import MongoDBJobStore
from pymongo import MongoClient
from backend.app.config import settings

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for scheduling recurring and one-time tasks."""
    
    def __init__(self):
        """Initialize scheduler."""
        jobstores = {}
        if getattr(settings, "MONGO_URI", None):
            client = MongoClient(settings.MONGO_URI)
            jobstores["default"] = MongoDBJobStore(database=settings.DB_NAME, collection="jobs", client=client)
        else:
            logger.warning("[Scheduler] No MONGO_URI, using default memory jobstore.")
            
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone="Asia/Kolkata",
            job_defaults={'misfire_grace_time': 300}
        )
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
        # Dead Man Switch: 5:35 AM IST every day
        self.scheduler.add_job(
            self._trigger_dead_man_check,
            CronTrigger(hour=5, minute=35, timezone="Asia/Kolkata"),
            id="dead_man_check",
            replace_existing=True
        )
        # Phase 6: Hourly habit engine tick
        self.scheduler.add_job(
            self._trigger_habit_engine,
            CronTrigger(minute=0, timezone="Asia/Kolkata"),
            id="habit_engine",
            replace_existing=True
        )
        # Phase 6: Daily Recap at 20:30
        self.scheduler.add_job(
            self._trigger_daily_recap,
            CronTrigger(hour=20, minute=30, timezone="Asia/Kolkata"),
            id="daily_recap",
            replace_existing=True
        )
        # Phase 6: Sunday Reflection at 22:00
        self.scheduler.add_job(
            self._trigger_sunday_reflection,
            CronTrigger(day_of_week='sun', hour=22, minute=0, timezone="Asia/Kolkata"),
            id="sunday_reflection",
            replace_existing=True
        )
        # Phase 6: Nightly Prediction at 01:00
        self.scheduler.add_job(
            self._trigger_nightly_prediction,
            CronTrigger(hour=1, minute=0, timezone="Asia/Kolkata"),
            id="nightly_prediction",
            replace_existing=True
        )
        # Phase 7: Weekly Radar at 09:00 on Sunday
        self.scheduler.add_job(
            self._trigger_weekly_radar,
            CronTrigger(day_of_week='sun', hour=9, minute=0, timezone="Asia/Kolkata"),
            id="weekly_radar",
            replace_existing=True
        )
        # Phase 6: Self-Test at 03:00
        self.scheduler.add_job(
            self._trigger_self_test,
            CronTrigger(hour=3, minute=0, timezone="Asia/Kolkata"),
            id="self_test",
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info(
            "Scheduler started: morning alarm 5:30 AM IST, "
            "night planning 10:30 PM IST, plus all Phase 6 jobs."
        )
        # Run custom catch-up policy
        asyncio.create_task(self._startup_catch_up())
    
    async def _startup_catch_up(self):
        """On server restart, process missed reminders."""
        try:
            from backend.app.db.database import db_manager
            if db_manager.db is None:
                return
            
            reminders = db_manager.db["reminders"]
            now = datetime.now(timezone.utc)
            thirty_mins_ago = now - timedelta(minutes=30)
            
            # Find all scheduled or awaiting_ack reminders whose due_ts is in the past
            cursor = reminders.find({
                "state": {"$in": ["scheduled", "awaiting_ack"]},
                "due_ts": {"$lt": now}
            })
            
            async for doc in cursor:
                reminder_id = str(doc["_id"])
                if doc["due_ts"] >= thirty_mins_ago:
                    logger.info(f"[Scheduler] Catch-up: Firing late reminder {reminder_id} immediately.")
                    # Inject an apology into the text if not already there
                    text = doc["text"]
                    if "late" not in text:
                        text = f"(Sorry boss, a few minutes late) {text}"
                        await reminders.update_one({"_id": doc["_id"]}, {"$set": {"text": text}})
                    
                    from backend.app.services.reminder_service import reminder_service
                    await reminder_service.trigger_reminder(reminder_id)
                else:
                    logger.info(f"[Scheduler] Catch-up: Parking old missed reminder {reminder_id}.")
                    await reminders.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"state": "parked", "updated_at": now}}
                    )
        except Exception as e:
            logger.error(f"[Scheduler] Catch-up policy failed: {e}")

    async def _trigger_morning_alarm(self):
        """Trigger morning alarm callback."""
        await self._log_job_run("morning_alarm")
        logger.info("SCHEDULER: Morning alarm triggered")
        if self._alarm_callback:
            asyncio.create_task(self._alarm_callback())
            
    async def _trigger_dead_man_check(self):
        """Checks if the alarm WebSocket check-in succeeded. If not, trigger FCM."""
        await self._log_job_run("dead_man_check")
        logger.info("SCHEDULER: Running dead man check (05:35 AM).")
        try:
            from backend.app.db.database import db_manager
            from datetime import datetime, timedelta, timezone
            
            if db_manager.db is None:
                return
                
            sessions = db_manager.db["sessions"]
            now = datetime.now(timezone.utc)
            ten_mins_ago = now - timedelta(minutes=10)
            
            # Look for a recent morning_alarm session
            recent_session = await sessions.find_one({
                "created_at": {"$gte": ten_mins_ago},
                "topic": "morning_alarm" # or whatever identifier we use
            })
            
            if not recent_session:
                logger.critical("[DEAD MAN] NO WAKE UP CHECK-IN DETECTED! ASTA may be force-stopped.")
                # We would import FCM and send a high-priority push here.
                # For Phase 4, we gracefully log the trigger since FCM depends on service-account.json
                logger.critical("[DEAD MAN] -> Triggering FCM high-priority payload (Simulated).")
        except Exception as e:
            logger.error(f"SCHEDULER: Dead man check failed: {e}")

    async def _trigger_night_planning(self):
        """Trigger night planning callback."""
        await self._log_job_run("night_planning")
        logger.info("SCHEDULER: Night planning triggered")
        if self._night_callback:
            asyncio.create_task(self._night_callback())

    async def _trigger_habit_engine(self):
        await self._log_job_run("habit_engine")
        logger.info("SCHEDULER: Habit engine tick triggered")
        try:
            from backend.app.services.habit_service import habit_service
            asyncio.create_task(habit_service.run_tick())
        except Exception as e:
            logger.error(f"Habit engine failed: {e}")

    async def _trigger_daily_recap(self):
        await self._log_job_run("daily_recap")
        logger.info("SCHEDULER: Daily recap triggered")
        try:
            from backend.app.services.reflection_service import reflection_service
            asyncio.create_task(reflection_service.run_daily_recap())
        except Exception as e:
            logger.error(f"Daily recap failed: {e}")

    async def _trigger_sunday_reflection(self):
        await self._log_job_run("sunday_reflection")
        logger.info("SCHEDULER: Sunday reflection triggered")
        try:
            from backend.app.services.reflection_service import reflection_service
            asyncio.create_task(reflection_service.run_sunday_reflection())
        except Exception as e:
            logger.error(f"Sunday reflection failed: {e}")

    async def _trigger_nightly_prediction(self):
        await self._log_job_run("nightly_prediction")
        logger.info("SCHEDULER: Nightly prediction triggered")
        try:
            from backend.app.services.proactive_service import proactive_service
            asyncio.create_task(proactive_service.run_nightly_prediction())
        except Exception as e:
            logger.error(f"Nightly prediction failed: {e}")

    async def _trigger_weekly_radar(self):
        await self._log_job_run("weekly_radar")
        logger.info("SCHEDULER: Weekly radar triggered")
        try:
            from backend.app.services.subscription_service import subscription_service
            asyncio.create_task(subscription_service.run_weekly_radar())
        except Exception as e:
            logger.error(f"Weekly radar failed: {e}")

    async def _trigger_self_test(self):
        await self._log_job_run("self_test")
        logger.info("SCHEDULER: Self test triggered")
        try:
            from backend.app.db.database import db_manager
            if db_manager.db is None:
                return
            
            job_runs = db_manager.db["job_runs"]
            now = datetime.now(timezone.utc)
            # Check if expected jobs ran yesterday (using UTC logical dates)
            yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            
            expected = ["morning_alarm", "dead_man_check", "daily_recap", "night_planning", "nightly_prediction"]
            missing = []
            for job in expected:
                doc = await job_runs.find_one({"job_id": job, "logical_date": yesterday_str})
                if not doc:
                    missing.append(job)
            
            if missing:
                logger.critical(f"[Self-Test] Silent scheduler death detected! Missed jobs yesterday: {missing}")
                # Escalate to reminder_service (to inject into morning brief)
                from backend.app.services.reminder_service import reminder_service
                await reminder_service.schedule_reminder(
                    text=f"Boss, critical system alert. Scheduler failed yesterday. Missed jobs: {', '.join(missing)}.",
                    due_ts=now + timedelta(minutes=5),
                    source="system"
                )
            else:
                logger.info("[Self-Test] All expected jobs ran yesterday. System healthy.")
        except Exception as e:
            logger.error(f"Self-test failed: {e}")

    async def _log_job_run(self, job_id: str):
        try:
            from backend.app.db.database import db_manager
            if db_manager.db is not None:
                job_runs = db_manager.db["job_runs"]
                now = datetime.now(timezone.utc)
                logical_date = now.strftime("%Y-%m-%d")
                await job_runs.update_one(
                    {"job_id": job_id, "logical_date": logical_date},
                    {"$set": {"last_run_at": now}},
                    upsert=True
                )
        except Exception:
            pass

    def add_one_time_reminder(
        self,
        reminder_id: str,
        run_at: datetime,
        callback,
        args=None
    ) -> bool:
        """Add a one-time reminder. Returns success status."""
        try:
            self.scheduler.add_job(
                callback,
                DateTrigger(run_date=run_at),
                id=reminder_id,
                args=args or [],
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
