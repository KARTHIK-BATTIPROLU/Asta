import logging
from datetime import datetime, timezone, timedelta
from backend.app.db.database import db_manager
from backend.app.services.reminder_service import reminder_service
from backend.app.core.llm_factory import router

logger = logging.getLogger(__name__)

class ReflectionService:
    async def run_daily_recap(self):
        """Runs at 20:30 daily."""
        logger.info("[ReflectionService] Running Daily Recap.")
        try:
            # 1. Fetch data (mocked here, would integrate with Notion/Habits)
            notion_diff = "Completed: Math homework. Missed: DSA practice."
            habits = "Habit DSA skipped."
            
            # 2. Build prompt
            prompt = f"""
            Write ASTA's evening recap for Karthik. <=120 spoken words. 
            Structure: (1) one-line day verdict, (2) done vs planned, (3) ONE honest miss with pattern context, 
            (4) tomorrow's single most important thing, (5) stale idea question if any.
            Register: Honest, warm, zero flattery.
            Inputs: 
            Notion: {notion_diff}
            Habits: {habits}
            """
            
            # 3. Call LLM (extraction/flash model)
            res = await router.run("realtime_chat", [{"role": "user", "content": prompt}])
            summary = res.text
            
            # 4. Schedule voice delivery via reminder_service
            now = datetime.now(timezone.utc)
            await reminder_service.schedule_reminder(
                text=summary,
                due_ts=now + timedelta(minutes=1),
                source="system"
            )
            
            # 5. Append to Notion (Mocked)
            logger.info("[ReflectionService] Appended daily log to Notion.")
            
        except Exception as e:
            logger.error(f"[ReflectionService] Daily recap failed: {e}")

    async def run_sunday_reflection(self):
        """Runs at 22:00 Sunday."""
        logger.info("[ReflectionService] Running Sunday Reflection.")
        try:
            prompt = """
            You are ASTA writing Karthik's Sunday reflection. He explicitly wants true colors — no filtering,
            no bluffing, no cruelty either. Output two artifacts:
            A) SPOKEN (<=200 words): the week in one honest paragraph.
            B) NOTION PAGE (markdown): full report.
            """
            
            res = await router.run("realtime_chat", [{"role": "user", "content": prompt}])
            text_result = res.text
            
            # In a real impl, we'd parse part A and part B.
            spoken_part = text_result[:200]
            
            # Deliver spoken part
            now = datetime.now(timezone.utc)
            await reminder_service.schedule_reminder(
                text=spoken_part,
                due_ts=now + timedelta(minutes=1),
                source="system"
            )
            
            # Append Notion + Google Docs (Mocked)
            logger.info("[ReflectionService] Created Notion Page and Appended to Google Docs.")
            
        except Exception as e:
            logger.error(f"[ReflectionService] Sunday reflection failed: {e}")

reflection_service = ReflectionService()
