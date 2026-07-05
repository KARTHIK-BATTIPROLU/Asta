import logging
import asyncio
from datetime import datetime
from backend.app.core.registry import registry
from backend.app.services.scheduler_service import scheduler_service
from backend.app.services.llm_service import stream_llm_response
from backend.app.api.ws_transport import broadcast_message, synthesize_proactive_audio_b64

logger = logging.getLogger("AccountabilityMonitor")

class AccountabilityMonitor:
    def __init__(self):
        self.session_id = "KARTHIK-BATTIPROLU"

    def schedule_next(self):
        """Schedules the monitor to run every 15 minutes using APScheduler"""
        try:
            scheduler_service.scheduler.add_job(
                self._run_check_wrapper,
                'interval',
                minutes=15,
                id='accountability_monitor_job',
                replace_existing=True
            )
            logger.info("[Accountability] Scheduled job every 15 minutes.")
        except Exception as e:
            logger.error(f"[Accountability] Failed to schedule job: {e}")

    def _run_check_wrapper(self):
        # apscheduler runs this synchronously (or asynchronously depending on executor), 
        # but we need an asyncio task.
        asyncio.create_task(self.run_check())

    async def run_check(self):
        logger.info("[Accountability] Running proactive check...")
        now = datetime.now()
        
        # 1. Are we in the 9 PM to 3 AM window?
        if now.hour >= 3 and now.hour < 21:
            logger.info("[Accountability] Outside 9 PM - 3 AM window. Skipping.")
            return
            
        # 2. Pull latest wellbeing snapshot from MongoDB
        db = registry.get("db")
        if not db or not db.mongo_client:
            logger.error("[Accountability] MongoDB not available.")
            return
            
        try:
            collection = db.get_collection("wellbeing")
            latest = await collection.find_one({}, sort=[("recorded_at", -1)])
            if not latest:
                logger.info("[Accountability] No wellbeing data found.")
                return
                
            top_apps = latest.get("topApps", [])
            
            entertainment_apps = ["com.instagram.android", "com.google.android.youtube", "com.zhiliaoapp.musically", "com.twitter.android"]
            excessive_entertainment = False
            for app in top_apps:
                if app.get("package_name") in entertainment_apps and app.get("minutes", 0) > 90:
                    excessive_entertainment = True
                    break
                    
            late_night_violation = (now.hour == 0 and now.minute > 30) or (now.hour == 1) or (now.hour == 2)
            
            if not excessive_entertainment and not late_night_violation:
                logger.info("[Accountability] No violations detected.")
                return
                
            # We have a violation! Determine escalation level.
            escalation_level = 1
            if hasattr(db, "neo4j_driver"):
                async with db.neo4j_driver.session() as session:
                    res = await session.run(
                        "MATCH (u:Identity {name: 'KARTHIK'})-[:EXHIBITED]->(b:Behavior {type: 'intervention'}) "
                        "WHERE b.timestamp > datetime() - duration('PT4H') "
                        "RETURN count(b) AS c"
                    )
                    record = await res.single()
                    if record and record["c"] > 0:
                        escalation_level = 2
                        
                    # Log this new intervention
                    await session.run(
                        "MATCH (u:Identity {name: 'KARTHIK'}) "
                        "CREATE (b:Behavior {type: 'intervention', timestamp: datetime(), level: $lvl}) "
                        "CREATE (u)-[:EXHIBITED]->(b)",
                        lvl=escalation_level
                    )
            
            if escalation_level == 1:
                response_text = "Boss, it's getting late and your screen time on entertainment apps is high. Time to wrap up and sleep."
            else:
                response_text = "Karthik! This is a strict warning. You are violating your late night screen time rules. Turn off the phone now and go to sleep!"
            
            logger.info(f"[Accountability] Triggering Level {escalation_level} intervention: {response_text}")
            
            audio_b64 = await synthesize_proactive_audio_b64(response_text)
            
            payload = {
                "type": "asta_proactive",
                "trigger": "accountability",
                "response": response_text,
                "escalation_level": escalation_level
            }
            if audio_b64:
                payload["audio_base64"] = audio_b64
                
            await broadcast_message(payload)
            
        except Exception as e:
            logger.error(f"[Accountability] Error during check: {e}")

monitor = AccountabilityMonitor()
