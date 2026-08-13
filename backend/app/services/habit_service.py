import logging
from datetime import datetime, timezone, timedelta
from backend.app.db.database import db_manager
from backend.app.services.reminder_service import reminder_service

logger = logging.getLogger(__name__)

class HabitService:
    def __init__(self):
        self.escalation_texts = {
            0: "Boss, just a gentle nudge: Did {name} happen today?",
            1: "Look, {name} is slipping. You promised yourself you'd do this.",
            2: "Okay, we need to negotiate. Why didn't {name} happen? Are we dropping this goal?",
            3: "Logging {name} as missed for the week. It'll be in Sunday's reflection. No judgment, just facts."
        }

    async def run_tick(self):
        """Called hourly by APScheduler."""
        logger.info("[HabitService] Hourly tick running.")
        try:
            if db_manager.db is None:
                return
            
            habits = db_manager.db["habits"]
            now = datetime.now(timezone.utc)
            
            # Simple simulation: Check all habits due today
            # A real implementation would parse 'schedule' (cron-like) and verify via HealthConnect/Notion
            async for habit in habits.find({"next_due": {"$lte": now}}):
                escalation_level = habit.get("escalation", 0)
                habit_name = habit["name"]
                
                # Check verification (simulated)
                verified = False 
                
                if not verified:
                    msg = self.escalation_texts.get(escalation_level, self.escalation_texts[3]).format(name=habit_name)
                    
                    # Schedule a reminder for the habit check
                    await reminder_service.schedule_reminder(
                        text=msg,
                        due_ts=now + timedelta(minutes=1),
                        source="habit"
                    )
                    
                    # Escalate for next time, cap at 3
                    next_level = min(escalation_level + 1, 3)
                    await habits.update_one(
                        {"_id": habit["_id"]},
                        {"$set": {
                            "escalation": next_level, 
                            "last_state_ts": now,
                            "next_due": now + timedelta(days=1)
                        }}
                    )
                else:
                    # De-escalate and celebrate
                    next_level = max(escalation_level - 1, 0)
                    streak = habit.get("streak", 0) + 1
                    await habits.update_one(
                        {"_id": habit["_id"]},
                        {"$set": {
                            "escalation": next_level,
                            "streak": streak,
                            "last_state_ts": now,
                            "next_due": now + timedelta(days=1)
                        }}
                    )
                    
            await self._run_2am_intervention(now)
            
        except Exception as e:
            logger.error(f"[HabitService] Tick failed: {e}")

    async def _run_2am_intervention(self, now: datetime):
        """Runs if the current time is around 2 AM IST."""
        ist_time = now + timedelta(hours=5, minutes=30)
        
        # We only run the intervention if it's strictly 02:00 hour
        if ist_time.hour == 2:
            logger.info("[HabitService] Running 2AM intervention check.")
            # Simulate usage stream indicating video app is open
            video_app_open = True
            
            if video_app_open:
                # Log intervention
                logger.info("[HabitService] Usage stream indicates active video app at 2 AM! Sending intervention.")
                await reminder_service.schedule_reminder(
                    text="Boss. Episode ends, phone sleeps, deal?",
                    due_ts=now + timedelta(minutes=1),
                    source="system"
                )
                
                # We should ensure this doesn't repeat for 45 mins.
                # In this simple implementation, the hourly tick only hits 02:00 once per day.

habit_service = HabitService()
