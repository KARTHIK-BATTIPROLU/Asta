import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from fastapi import FastAPI, WebSocket, Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any, Union
from backend.app.config import settings  # Updated to use new settings
from backend.app.db.database import db_manager
from backend.app.api.ws_transport import router as ws_router
from backend.app.api.routes import router as api_router
from backend.app.api.preferences import router as preferences_router
from backend.app.api.content import router as content_router
from backend.app.api.health import router as health_router
from backend.app.auth.token_auth import verify_bearer_and_device as verify_token
from backend.app.core.registry import registry
from backend.app.core.circuit_breaker import status_registry
from backend.app.services.embedding import EmbeddingService
from backend.app.services.memory_orchestrator import orchestrator
from backend.app.services.llm_service import stream_llm_response
from starlette.middleware.base import BaseHTTPMiddleware
from redis import asyncio as aioredis
import time, os
import uuid
from fastapi.responses import StreamingResponse
import json

# Import new memory layer
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from memory import memory_engine

# Pre-load sentence-transformers model at startup (loads once, not on first request)
from memory import embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ASTA_MVE")

# Try to use uvloop for better performance
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    logger.info("Using uvloop event loop policy")
except ImportError:
    pass

app = FastAPI(
    title="ASTA Engine",
    description="Advanced System for Task Automation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def tat_middleware(request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    logger.info(f"TAT [HTTP]: {request.method} {request.url.path} completed in {process_time:.4f}s")
    return response

app.include_router(ws_router)
app.include_router(api_router, prefix="/api")
app.include_router(preferences_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(health_router, prefix="/api")
from backend.app.api import settings_routes
app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
from backend.app.api import ws_transport
from backend.app.api import sync_routes

# Note: WS routes are registered inside ws_transport
app.include_router(sync_routes.router, prefix="/api/v1", tags=["sync"])


@app.get("/api/me")
async def me(user=Depends(verify_token)):
    return {"user": user, "status": "ASTA online"}


@app.get("/api/ngrok-url")
async def get_ngrok_url():
    """
    Endpoint to dynamically fetch the current ngrok URL.
    This allows the Android app to auto-configure itself.
    """
    try:
        import requests
        response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=3)
        response.raise_for_status()
        
        data = response.json()
        tunnels = data.get('tunnels', [])
        
        if not tunnels:
            return JSONResponse(
                status_code=503,
                content={"error": "No active ngrok tunnels found"}
            )
        
        # Find HTTPS tunnel
        for tunnel in tunnels:
            if tunnel.get('proto') == 'https':
                public_url = tunnel.get('public_url', '')
                if not public_url.endswith('/'):
                    public_url += '/'
                return {"url": public_url, "status": "active"}
        
        # Fallback to first tunnel
        public_url = tunnels[0].get('public_url', '')
        if not public_url.endswith('/'):
            public_url += '/'
        return {"url": public_url, "status": "active"}
        
    except Exception as e:
        logger.error(f"Failed to fetch ngrok URL: {e}")
        return JSONResponse(
            status_code=503,
            content={"error": f"Failed to fetch ngrok URL: {str(e)}"}
        )


@app.get("/health/memory")
async def memory_health():
    """Memory layer health check endpoint."""
    return await memory_engine.health_check()

class ChatCompletionMessage(BaseModel):
    role: str
    content: Union[str, List[Any]]

    model_config = ConfigDict(extra='allow')

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatCompletionMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    user: Optional[str] = "openclaw_default"

    model_config = ConfigDict(extra='allow')

@app.post("/v1/chat/completions")
async def chat_completions_adapter(request: ChatCompletionRequest, token: str = Depends(verify_token)):
    # 1. CLEAN THE PROMPT
    raw_content = request.messages[-1].content
    if isinstance(raw_content, list):
        user_query = next((item['text'] for item in raw_content if item.get('type') == 'text'), str(raw_content))
    else:
        user_query = raw_content
    
    if "]" in user_query:
        user_query = user_query.split("]")[-1].strip()

    session_id = request.user or "openclaw_default"

    try:
        # 2. Trigger Memory
        context = await orchestrator.cross_tier_retrieve(user_query, top_k=3)
        memory_mode = status_registry.get_memory_mode()
        
        # 3. STREAMING GENERATOR (The Fix)
        async def event_generator():
            full_text = ""
            async for chunk in stream_llm_response(
                user_message=user_query,
                session_id=session_id,
                rag_context=context,
                health_status=memory_mode
            ):
                if chunk:
                    full_text += chunk
                    # Format exactly like an OpenAI stream chunk
                    chunk_data = {
                        "id": f"chatcmpl-{uuid.uuid4()}",
                        "object": "chat.completion.chunk",
                        "model": request.model,
                        "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
            
            print(f"\n[STREAM SUCCESS] ASTA sent: {full_text[:50]}...")
            yield "data: [DONE]\n\n"

        # 4. RETURN THE STREAM
        if request.stream:
            return StreamingResponse(event_generator(), media_type="text/event-stream")
        else:
            # Fallback if it somehow asks for non-streamed
            return {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "model": request.model,
                "choices": [{"message": {"role": "assistant", "content": "Stream fallback triggered."}}]
            }

    except Exception as e:
        print(f"BRIDGE CRASH: {str(e)}")
        return {"choices": [{"message": {"role": "assistant", "content": f"System Error: {str(e)}" }}]}
    

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing MVE Core Services...")
    
    # 0. Environment Validation & Core Libs (Fail-Fast)
    try:
        from backend.app.core.env_validation import validate_environment
        validate_environment()
        
        # Verify absolute core dependencies
        import graphiti_core
        import pipecat
        import langchain_core
        import groq
        import apscheduler
    except Exception as e:
        logger.critical(f"Startup Terminated due to Environment/Core Lib Validation Failure: {e}")
        # Re-raise to prevent uvicorn from starting up broken
        raise RuntimeError(f"Core dependency missing: {e}")
    
    # 1. Spacy Validation
    try:
        import spacy
        spacy.load("en_core_web_sm")
        logger.info("NLP Engine (Spacy) validated.")
    except Exception as e:
        logger.warning(f"Degraded Mode Status: Spacy model missing or failed ({e}). Run: python -m spacy download en_core_web_sm")

    # 2. Database & Neo4j Validation
    try:
        await db_manager.connect()
        registry.register("db", db_manager)
        health = await db_manager.ping()
        if not health:
             logger.warning("Degraded Mode Status: Database Health Check Failed! Some systems may run offline.")
             
        # Optional: Direct Neo4j Check if defined in registry or memory_handler
        from backend.app.config import settings
        if not settings.NEO4J_URI or not settings.NEO4J_PASSWORD:
            logger.warning("Degraded Mode Status: Neo4j Aura credentials missing from environment.")
        else:
            from backend.app.services.memory.graph_ltm import graph_ltm
            await graph_ltm.initialize()
            if not graph_ltm.is_initialized:
                logger.warning("Degraded Mode Status: Graphiti/Neo4j L2 graph memory failed to initialize.")
    except Exception as e:
        logger.error(f"Degraded Mode Status: Failed to bind critical Polyglot Persistence endpoints! {e}")
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_pool = aioredis.from_url(redis_url, decode_responses=True)
        # Test connection
        await redis_pool.ping()
        registry.register("redis", redis_pool)
        logger.info(f"Connected to Redis at {redis_url}")
    except Exception as redis_err:
        logger.warning(f"Redis connection failed (session state will be degraded): {redis_err}")
        registry.register("redis", None)  # Explicitly set to None for graceful degradation
    
    try:
        embedding_service = EmbeddingService()
        registry.register("embedding", embedding_service)
        logger.info("Semantic Memory (Vector) loaded.")
    except Exception as e:
        logger.error(f"Vector Memory initialization failed: {e}")

    # Initialize Pinecone vector store for RAG upserts + queries
    try:
        if settings.PINECONE_API_KEY:
            from pinecone import Pinecone

            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            pinecone_index = pc.Index(settings.PINECONE_INDEX_NAME)

            class PineconeVectorSearch:
                """Thin async wrapper around the Pinecone gRPC/REST index."""
                def __init__(self, index):
                    self._index = index

                async def upsert(self, id: str, vector: list, metadata: dict):
                    await asyncio.to_thread(
                        self._index.upsert,
                        vectors=[(id, vector, metadata)]
                    )

                async def query(self, vector: list, top_k: int = 5, **kwargs):
                    return await asyncio.to_thread(
                        self._index.query,
                        vector=vector, top_k=top_k, include_metadata=True, **kwargs
                    )

            registry.register("vector", PineconeVectorSearch(pinecone_index))
            logger.info(f"Pinecone vector store registered (index: {settings.PINECONE_INDEX_NAME}).")

            # Validate index dimensions match embedding model
            try:
                stats = await asyncio.to_thread(pinecone_index.describe_index_stats)
                vector_count = stats.get("total_vector_count", 0) if isinstance(stats, dict) else getattr(stats, "total_vector_count", 0)
                dimension = stats.get("dimension", 0) if isinstance(stats, dict) else getattr(stats, "dimension", 0)
                logger.info(f"[RAG] Pinecone index stats: {vector_count} vectors, dimension={dimension}")
                if dimension and dimension != settings.PINECONE_EMBEDDING_DIM:
                    logger.error(
                        f"[RAG] ⚠️ DIMENSION MISMATCH: Pinecone index has dim={dimension}, "
                        f"but embedding model produces dim={settings.PINECONE_EMBEDDING_DIM}. "
                        f"Queries will fail!"
                    )
            except Exception as stats_err:
                logger.warning(f"[RAG] Could not validate Pinecone index stats: {stats_err}")
        else:
            logger.warning("PINECONE_API_KEY not set. RAG vector upserts/queries disabled.")
    except Exception as e:
        logger.warning(f"Pinecone initialization failed (RAG disabled): {e}")

    # Legacy Neo4j base graph initialization removed to retire the second Neo4j schema

    # Initialize Session Manager context
    try:
        from backend.app.services.session_manager import SessionManager
        await SessionManager.restore_active_sessions()
        await SessionManager.start_workers()
    except Exception as e:
        logger.warning(f"SessionManager startup failed: {e}")

    # Start outbox worker for async memory extraction
    try:
        from backend.app.core.outbox_worker import start_outbox_worker
        start_outbox_worker()
        logger.info("Outbox worker started")
    except Exception as e:
        logger.warning(f"Outbox worker startup failed: {e}")

    # Saga Retry Worker removed in Phase 0

    # Initialize Wake Word Detection Service
    try:
        from backend.app.services.wake_word_service import initialize_wake_word_service
        from backend.app.config import settings
        
        if settings.WAKE_WORD_ENABLED:
            wake_word_service = initialize_wake_word_service(
                wake_words=settings.WAKE_WORD_MODELS.split(","),
                threshold=settings.WAKE_WORD_THRESHOLD,
                enabled=True
            )
            if wake_word_service and wake_word_service.is_ready():
                wake_word_service.set_cooldown(settings.WAKE_WORD_COOLDOWN)
                logger.info(f"Wake Word Detection initialized with models: {settings.WAKE_WORD_MODELS}")
            else:
                logger.warning("Wake Word Detection failed to initialize")
        else:
            logger.info("Wake Word Detection disabled (WAKE_WORD_ENABLED=false)")
    except Exception as e:
        logger.warning(f"Wake Word Detection initialization failed: {e}")

    # Register Stage 2 API tools
    try:
        from backend.app.tools.tool_registry import register_all_tools
        register_all_tools()
    except Exception as e:
        logger.warning(f"ToolRegistry startup failed: {e}")

    # Initialize new memory layer
    try:
        memory_status = await memory_engine.connect_all()
        logger.info(f"Memory layer: {memory_status}")
    except Exception as e:
        logger.error(f"Memory layer startup failed: {e}")

    # Initialize LangGraph checkpointer (PostgreSQL, falls back to in-memory)
    try:
        from backend.app.core.checkpointer import init_checkpointer
        from backend.app.core.supervisor_graph import get_supervisor_graph
        await init_checkpointer()
        get_supervisor_graph()  # compile once now that the checkpointer is ready
        logger.info("Supervisor graph + checkpointer initialized")
    except Exception as e:
        logger.error(f"Checkpointer/supervisor init failed: {e}")
    
    # Initialize and start scheduler
    try:
        from backend.app.services.scheduler_service import scheduler_service
        from backend.app.core.supervisor_graph import run_supervisor_graph
        import uuid

        # Morning alarm callback — fires when scheduler triggers 5:30 AM
        async def morning_alarm_callback():
            try:
                session_id = f"alarm-{uuid.uuid4().hex[:8]}"
                result = await run_supervisor_graph(
                    session_id=session_id,
                    user_input="morning alarm triggered, give me my morning brief",
                )
                logger.info(f"Morning alarm triggered: {result.get('response', '')[:100]}")

                # Try to broadcast to WebSocket clients if available
                try:
                    from backend.app.api.ws_transport import broadcast_message
                    await broadcast_message({
                        "type": "asta_proactive",
                        "trigger": "morning_alarm",
                        "response": result.get("response", ""),
                        "audio_needed": True
                    })
                except Exception as broadcast_err:
                    logger.debug(f"WebSocket broadcast not available: {broadcast_err}")
            except Exception as e:
                logger.error(f"Morning alarm callback failed: {e}")

        # Night planning callback — fires at 10:30 PM
        async def night_planning_callback():
            try:
                session_id = f"night-{uuid.uuid4().hex[:8]}"
                result = await run_supervisor_graph(
                    session_id=session_id,
                    user_input="night planning session starting",
                )
                logger.info(f"Night planning triggered: {result.get('response', '')[:100]}")

                # Try to broadcast to WebSocket clients if available
                try:
                    from backend.app.api.ws_transport import broadcast_message
                    await broadcast_message({
                        "type": "asta_proactive",
                        "trigger": "night_planning",
                        "response": result.get("response", ""),
                        "audio_needed": True
                    })
                except Exception as broadcast_err:
                    logger.debug(f"WebSocket broadcast not available: {broadcast_err}")
            except Exception as e:
                logger.error(f"Night planning callback failed: {e}")
        
        scheduler_service.set_alarm_callback(morning_alarm_callback)
        scheduler_service.set_night_callback(night_planning_callback)
        scheduler_service.start()
        logger.info("Scheduler started: morning alarm 5:30 AM IST, night planning 10:30 PM IST")

        from backend.app.workflows.accountability_monitor import monitor
        monitor.schedule_next()
    except Exception as e:
        logger.error(f"Scheduler startup failed: {e}")

    # Reload pending reminders for today (APScheduler's in-memory job store doesn't
    # survive a restart, so any future reminder needs to be re-registered here).
    try:
        from datetime import date as _date
        from backend.app.services.notion_service import notion_service
        from backend.app.workflows.task_manager import _schedule_reminder

        today_str = _date.today().isoformat()
        pending = await notion_service.get_pending_tasks(today_str)
        rescheduled = 0
        for t in pending:
            if t.get("status") == "Reminded":
                continue
            if _schedule_reminder(t["page_id"], t["task_name"], t.get("scheduled_time", ""), today_str):
                rescheduled += 1
        logger.info(f"Reminder reload: {rescheduled}/{len(pending)} pending task(s) re-scheduled")
    except Exception as e:
        logger.error(f"Reminder reload failed: {e}")
    
    # Seed initial data if needed
    try:
        from backend.app.utils.seed_data import seed_if_empty
        await seed_if_empty()
    except Exception as e:
        logger.warning(f"Seed data check failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down MVE...")
    
    # Stop scheduler
    try:
        from backend.app.services.scheduler_service import scheduler_service
        scheduler_service.stop()
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Scheduler shutdown error: {e}")
    
    # Shutdown new memory layer
    try:
        await memory_engine.disconnect_all()
    except Exception as e:
        logger.error(f"Memory layer shutdown error: {e}")

    # Close LangGraph checkpointer (Postgres pool)
    try:
        from backend.app.core.checkpointer import close_checkpointer
        await close_checkpointer()
    except Exception as e:
        logger.error(f"Checkpointer shutdown error: {e}")
    
    try:
        embedding_service = registry.get("embedding")
        if embedding_service and hasattr(embedding_service, "shutdown"):
            embedding_service.shutdown()
    except Exception as e:
        logger.warning(f"Embedding service shutdown error: {e}")

    # Saga drain removed in Phase 0
    try:
        from backend.app.core.outbox_worker import stop_outbox_worker
        await stop_outbox_worker()
    except Exception as e:
        logger.warning(f"Outbox worker shutdown error: {e}")

    try:
        from backend.app.services.session_manager import SessionManager
        await SessionManager.stop_workers()
    except Exception as e:
        logger.warning(f"Error stopping session manager workers: {e}")
        
    try:
        from backend.app.core.task_registry import TaskRegistry
        logger.info(f"Draining {TaskRegistry.active_count()} background tasks...")
        await TaskRegistry.shutdown(cancel_timeout=3.0)
    except Exception as e:
        logger.warning(f"TaskRegistry shutdown error: {e}")
    await db_manager.disconnect()
    
    redis_pool = registry.get("redis")
    if redis_pool:
        await redis_pool.close()
