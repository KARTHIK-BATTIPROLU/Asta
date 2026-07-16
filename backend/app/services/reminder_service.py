import logging
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from backend.app.db.database import db_manager
from backend.app.services.scheduler_service import scheduler_service
from backend.app.api.ws_transport import broadcast_message, _active_connections

logger = logging.getLogger(__name__)

class ReminderService:
    """
    Manages reminders, state transitions, and delivery logic.
    Delivery Ladder:
      - check if WS alive (user is in a call) -> inject speak
      - else -> FCM push (simulated)
    """
    
    def __init__(self):
        self.max_retries = 3
        self.ack_timeout_seconds = 60
        self.retry_interval_minutes = 5
        self.silent_window_start = 9 # 09:00
        self.silent_window_end = 16  # 16:00
        
    def _generate_dedupe_key(self, text: str, due_ts: datetime) -> str:
        """Hash(text_norm, due_ts_bucket). Bucket by minute to avoid duplicates."""
        text_norm = text.lower().strip()
        bucket = due_ts.replace(second=0, microsecond=0).isoformat()
        return hashlib.sha256(f"{text_norm}_{bucket}".encode()).hexdigest()

    async def schedule_reminder(self, text: str, due_ts: datetime, source: str = "voice") -> str:
        """Schedules a new reminder in MongoDB and APScheduler."""
        reminders = db_manager.db["reminders"]
        dedupe_key = self._generate_dedupe_key(text, due_ts)
        
        doc = {
            "text": text,
            "due_ts": due_ts,
            "source": source,
            "state": "scheduled",
            "attempts": 0,
            "dedupe_key": dedupe_key,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        try:
            res = await reminders.insert_one(doc)
            reminder_id = str(res.inserted_id)
            
            # Add to APScheduler
            scheduler_service.add_one_time_reminder(
                reminder_id=reminder_id,
                run_at=due_ts,
                callback=self.trigger_reminder,
                args=[reminder_id]
            )
            logger.info(f"[ReminderService] Scheduled reminder {reminder_id} for {due_ts}")
            return reminder_id
        except Exception as e:
            logger.error(f"[ReminderService] Error scheduling reminder: {e}")
            return ""

    async def trigger_reminder(self, reminder_id: str):
        """Called by APScheduler when due_ts is reached."""
        reminders = db_manager.db["reminders"]
        doc = await reminders.find_one({"_id": db_manager.ObjectId(reminder_id)})
        if not doc:
            return
            
        if doc["state"] in ["acked", "parked"]:
            return

        attempts = doc.get("attempts", 0) + 1
        
        # Check Silent Window (Weekdays 09:00 - 16:00)
        now = datetime.now(timezone.utc)
        is_weekday = now.weekday() < 5
        # Assuming IST for silent window check
        ist_hour = (now + timedelta(hours=5, minutes=30)).hour
        is_silent = is_weekday and (self.silent_window_start <= ist_hour < self.silent_window_end)

        if attempts > self.max_retries:
            logger.info(f"[ReminderService] Reminder {reminder_id} max retries reached. Parking.")
            await reminders.update_one(
                {"_id": doc["_id"]},
                {"$set": {"state": "parked", "updated_at": now}}
            )
            return

        await reminders.update_one(
            {"_id": doc["_id"]},
            {"$set": {"state": "speaking", "attempts": attempts, "updated_at": now}}
        )

        ws_alive = len(_active_connections) > 0
        
        if ws_alive and not is_silent:
            logger.info(f"[ReminderService] WS alive, injecting reminder {reminder_id} via voice.")
            payload = {
                "t": "speak",
                "text": f"Boss, quick reminder: {doc['text']}",
                "requires_ack": True,
                "reminder_id": reminder_id
            }
            await broadcast_message(payload)
            # We don't have true turn-aware injection in this simple mock, but it broadcasts.
        else:
            if is_silent:
                logger.info(f"[ReminderService] Silent window active. Sending silent FCM for {reminder_id}.")
            else:
                logger.info(f"[ReminderService] WS dead. Sending high-priority FCM for {reminder_id}.")
            # Simulating FCM
            # ... FCM implementation ...
            pass
            
        # Transition to awaiting_ack
        await reminders.update_one(
            {"_id": doc["_id"]},
            {"$set": {"state": "awaiting_ack", "updated_at": datetime.now(timezone.utc)}}
        )
        
        # Schedule unacked check
        asyncio.create_task(self._check_unacked(reminder_id))

    async def _check_unacked(self, reminder_id: str):
        """Waits 60s, then checks if still awaiting_ack. If so, triggers next step in ladder."""
        await asyncio.sleep(self.ack_timeout_seconds)
        reminders = db_manager.db["reminders"]
        doc = await reminders.find_one({"_id": db_manager.ObjectId(reminder_id)})
        if not doc or doc["state"] != "awaiting_ack":
            return
            
        logger.warning(f"[ReminderService] Reminder {reminder_id} unacked after 60s. Re-triggering via FCM/Retry.")
        
        # Schedule next retry in 5 minutes
        next_run = datetime.now(timezone.utc) + timedelta(minutes=self.retry_interval_minutes)
        scheduler_service.add_one_time_reminder(
            reminder_id=f"{reminder_id}_retry_{doc['attempts']}",
            run_at=next_run,
            callback=self.trigger_reminder,
            args=[reminder_id]
        )

    async def ack_reminder(self, reminder_id: str, method: str = "voice"):
        """Called when user acks via voice, button, or tap."""
        reminders = db_manager.db["reminders"]
        res = await reminders.update_one(
            {"_id": db_manager.ObjectId(reminder_id)},
            {"$set": {"state": "acked", "updated_at": datetime.now(timezone.utc), "ack_method": method}}
        )
        if res.modified_count > 0:
            logger.info(f"[ReminderService] Reminder {reminder_id} acked via {method}.")
            return True
        return False

reminder_service = ReminderService()
