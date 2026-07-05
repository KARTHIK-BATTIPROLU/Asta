from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import logging
from backend.app.core.registry import registry
from backend.app.api.dependencies import get_api_key

router = APIRouter()
logger = logging.getLogger("MetricsRoutes")

class AppUsage(BaseModel):
    package_name: str
    minutes_used: int

class DailyMetricsPayload(BaseModel):
    date_iso: str
    top_apps: List[AppUsage]
    total_screen_time_minutes: int
    step_count: Optional[int] = 0
    sleep_minutes: Optional[int] = 0

@router.post("/metrics/daily")
async def receive_daily_metrics(
    payload: DailyMetricsPayload,
    _=Depends(get_api_key)
):
    """
    Receives daily metrics from the Android worker (sent at 11:30 PM).
    Persists to L4 memory (Neo4j).
    """
    try:
        db = registry.get("db")
        if not db or not hasattr(db, "neo4j_driver"):
            logger.warning("[Metrics] Neo4j not available. Discarding metrics.")
            return {"status": "error", "message": "Database not configured"}

        async with db.neo4j_driver.session() as session:
            # Create a DailyMetrics node and link it to Karthik
            query = """
            MATCH (u:Identity {name: 'KARTHIK'})
            CREATE (m:DailyMetrics {
                date: $date_iso,
                screen_time_minutes: $screen_time,
                step_count: $step_count,
                sleep_minutes: $sleep_minutes,
                recorded_at: datetime()
            })
            CREATE (u)-[:RECORDED_ON]->(m)
            """
            
            # Create sub-nodes for top apps
            app_queries = []
            for app in payload.top_apps:
                app_queries.append(f"""
                MATCH (m:DailyMetrics {{date: '{payload.date_iso}'}})
                MERGE (a:App {{package_name: '{app.package_name}'}})
                CREATE (m)-[:USED_APP {{minutes: {app.minutes_used}}}]->(a)
                """)
            
            await session.run(
                query,
                date_iso=payload.date_iso,
                screen_time=payload.total_screen_time_minutes,
                step_count=payload.step_count,
                sleep_minutes=payload.sleep_minutes
            )
            
            # Execute app relationships
            for aq in app_queries:
                await session.run(aq)

        logger.info(f"[Metrics] Successfully logged metrics for {payload.date_iso}")
        return {"status": "success"}

    except Exception as e:
        logger.error(f"[Metrics] Error saving to Neo4j: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
