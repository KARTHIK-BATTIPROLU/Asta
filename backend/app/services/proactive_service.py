import logging
from datetime import datetime, timezone, timedelta
from backend.app.db.database import db_manager
from backend.app.core.llm_factory import router
from backend.app.services.reminder_service import reminder_service

logger = logging.getLogger(__name__)

class ProactiveService:
    async def run_nightly_prediction(self):
        """Runs at 01:00 to prep docs/research for tomorrow's plan."""
        logger.info("[ProactiveService] Running Nightly Prediction.")
        try:
            # 1. Fetch open loops / Notion plan (Mocked)
            loops = "Build database auth logic."
            
            prompt = f"""
            Given these open loops: {loops}
            What <=2 things will Karthik likely need prepared tomorrow? 
            Just return a brief plan.
            """
            
            res = await router.run("realtime_chat", [{"role": "user", "content": prompt}])
            logger.info(f"[ProactiveService] Nightly prediction plan: {res.text}")
            
            # Simulated Research execution
            logger.info("[ProactiveService] Pre-running research-lite into draft Notion page.")
            
        except Exception as e:
            logger.error(f"[ProactiveService] Nightly prediction failed: {e}")
            
    async def monitor_signals(self):
        """Called periodically or triggered by events to check for stale ideas, contradictions, etc."""
        # E.g. deadline_risk, contradiction severity >= 4, health streak
        # For Phase 6, this is a placeholder structure
        pass

proactive_service = ProactiveService()
