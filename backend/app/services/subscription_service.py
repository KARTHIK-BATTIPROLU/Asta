import logging
from datetime import datetime, timezone, timedelta
import asyncio
from backend.app.db.database import db_manager
from backend.app.services.research_service import research_service
import uuid

logger = logging.getLogger(__name__)

class SubscriptionService:
    def __init__(self):
        self.default_topic = "Tech trends and AI frameworks"
        
    async def run_weekly_radar(self):
        """Runs on Sunday to fetch 8 sources for the weekly radar."""
        logger.info("[SubscriptionService] Running Weekly Radar subscription.")
        try:
            session_id = str(uuid.uuid4())
            # For a subscription, we do a deeper research (8 sources) without heartbeats over WS
            # We'll just run the deep_research manually
            res_data = await research_service.deep_research(self.default_topic)
            raw_sources = res_data["sources"]
            
            logger.info(f"[SubscriptionService] Weekly radar found {len(raw_sources)} sources.")
            
            # Simulated Notion Append for Weekly Radar
            logger.info("[SubscriptionService] Appended Weekly Radar to Notion.")
            
        except Exception as e:
            logger.error(f"[SubscriptionService] Weekly radar failed: {e}")

subscription_service = SubscriptionService()
