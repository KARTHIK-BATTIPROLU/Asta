"""
ASTA Health API
Health check endpoints for monitoring system status.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from backend.app.api.routes import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check():
    """Basic health check endpoint (public)."""
    return {
        "status": "ok",
        "service": "ASTA Backend",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/deep")
async def deep_health_check(token: str = Depends(verify_token)):
    """
    Deep health check - tests all critical connections.
    Requires authentication.
    """
    health_status = {
        "overall": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check MongoDB
    try:
        from backend.app.db.database import db_manager
        db = db_manager.db
        await db.command("ping")
        health_status["services"]["mongodb"] = {
            "status": "ok",
            "message": "Connected"
        }
    except Exception as e:
        health_status["services"]["mongodb"] = {
            "status": "error",
            "message": str(e)
        }
        health_status["overall"] = "degraded"
    
    # Check Redis
    try:
        import redis.asyncio as aioredis
        from backend.app.config import settings
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
        health_status["services"]["redis"] = {
            "status": "ok",
            "message": "Connected"
        }
    except Exception as e:
        health_status["services"]["redis"] = {
            "status": "error",
            "message": str(e)
        }
        health_status["overall"] = "degraded"
    
    # Check Neo4j
    try:
        from memory.l2_graph import graph_store
        result = await graph_store.query("RETURN 1 as test")
        health_status["services"]["neo4j"] = {
            "status": "ok",
            "message": "Connected"
        }
    except Exception as e:
        health_status["services"]["neo4j"] = {
            "status": "error",
            "message": str(e)
        }
        health_status["overall"] = "degraded"
    
    # Check Pinecone
    try:
        from memory.l3_vectors import vector_store
        stats = await vector_store.get_stats()
        health_status["services"]["pinecone"] = {
            "status": "ok",
            "message": "Connected",
            "vector_count": stats.get("total_vector_count", 0)
        }
    except Exception as e:
        health_status["services"]["pinecone"] = {
            "status": "error",
            "message": str(e)
        }
        health_status["overall"] = "degraded"
    
    return health_status


@router.get("/memory")
async def memory_health_check(token: str = Depends(verify_token)):
    """
    Memory layer health check.
    Requires authentication.
    """
    try:
        from memory import memory_engine
        health = await memory_engine.health_check()
        return health
    except Exception as e:
        logger.error(f"Memory health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Memory health check failed: {str(e)}"
        )


@router.get("/scheduler")
async def scheduler_health_check(token: str = Depends(verify_token)):
    """
    Scheduler health check - shows scheduled jobs and next run times.
    Requires authentication.
    """
    try:
        from backend.app.services.scheduler_service import scheduler_service
        
        jobs = []
        for job in scheduler_service.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "status": "ok",
            "scheduler_running": scheduler_service.scheduler.running,
            "jobs": jobs,
            "job_count": len(jobs),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Scheduler health check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/llm")
async def llm_health_check(token: str = Depends(verify_token)):
    """
    LLM health check - tests model availability.
    Requires authentication.
    """
    try:
        from backend.app.core.llm_factory import llm_router
        
        # Test a simple invocation
        result = await llm_router.invoke_with_system(
            "quick_response",
            "You are a health check bot. Respond with exactly: 'OK'",
            "Health check"
        )
        
        return {
            "status": "ok",
            "message": "LLM responding",
            "test_response": result.strip(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"LLM health check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/services")
async def services_health_check(token: str = Depends(verify_token)):
    """
    Check health of all supporting services.
    Requires authentication.
    """
    services_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check Notion
    try:
        from backend.app.services.notion_service import notion_service
        from backend.app.config import settings
        if settings.NOTION_API_KEY:
            services_status["services"]["notion"] = {
                "status": "configured",
                "message": "API key present"
            }
        else:
            services_status["services"]["notion"] = {
                "status": "not_configured",
                "message": "API key missing"
            }
    except Exception as e:
        services_status["services"]["notion"] = {
            "status": "error",
            "message": str(e)
        }
    
    # Check Weather
    try:
        from backend.app.services.weather_service import weather_service
        weather = await weather_service.get_weather("Hyderabad")
        services_status["services"]["weather"] = {
            "status": "ok",
            "message": f"Current temp: {weather.get('temp_c')}°C"
        }
    except Exception as e:
        services_status["services"]["weather"] = {
            "status": "error",
            "message": str(e)
        }
    
    # Check Research Service
    try:
        from backend.app.services.research_service import research_service
        from backend.app.config import settings
        if settings.SERPER_API:
            services_status["services"]["research"] = {
                "status": "configured",
                "message": "Serper API key present"
            }
        else:
            services_status["services"]["research"] = {
                "status": "not_configured",
                "message": "Serper API key missing"
            }
    except Exception as e:
        services_status["services"]["research"] = {
            "status": "error",
            "message": str(e)
        }
    
    return services_status
