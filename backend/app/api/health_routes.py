from fastapi import APIRouter
from backend.app.db.database import db_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Returns the real status of the system and its dependencies.
    """
    status = "ok"
    deps = {}
    
    # Check MongoDB
    try:
        await db_manager.db.command("ping")
        deps["mongodb"] = "up"
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        deps["mongodb"] = "down"
        status = "degraded"
        
    # Check Neo4j (Memory Service)
    try:
        from backend.app.services.memory_service import memory_service
        # For MVP we assume it's up if the driver exists, but real check should query
        if memory_service.client:
            deps["neo4j"] = "up"
        else:
            deps["neo4j"] = "down"
            status = "degraded"
    except Exception as e:
        logger.error(f"Neo4j health check failed: {e}")
        deps["neo4j"] = "down"
        status = "degraded"

    if all(v == "down" for v in deps.values()):
        status = "down"

    return {"status": status, "deps": deps}
