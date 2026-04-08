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
from backend.app.config import config
from backend.app.db.mongo import MongoDB
from backend.app.db.database import db_manager
from backend.app.api.ws_routes import router as ws_router
from backend.app.api.routes import router as api_router
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ASTA_MVE")

app = FastAPI(title="ASTA Realtime MVE")

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

security = HTTPBearer()

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

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != "asta-local-key":
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

@app.post("/v1/chat/completions")
async def chat_completions_adapter(request: ChatCompletionRequest):
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
        MongoDB.connect()
        health = await db_manager.ping()
        if not health:
             logger.warning("Degraded Mode Status: Database Health Check Failed! Some systems may run offline.")
             
        # Optional: Direct Neo4j Check if defined in registry or memory_handler
        from backend.app.config import config
        if not config.NEO4J_URI or not config.NEO4J_PASSWORD:
            logger.warning("Degraded Mode Status: Neo4j Aura credentials missing from environment.")
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
        if config.PINECONE_API_KEY:
            from pinecone import Pinecone

            pc = Pinecone(api_key=config.PINECONE_API_KEY)
            pinecone_index = pc.Index(config.PINECONE_INDEX_NAME)

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
            logger.info(f"Pinecone vector store registered (index: {config.PINECONE_INDEX_NAME}).")

            # Validate index dimensions match embedding model
            try:
                stats = await asyncio.to_thread(pinecone_index.describe_index_stats)
                vector_count = stats.get("total_vector_count", 0) if isinstance(stats, dict) else getattr(stats, "total_vector_count", 0)
                dimension = stats.get("dimension", 0) if isinstance(stats, dict) else getattr(stats, "dimension", 0)
                logger.info(f"[RAG] Pinecone index stats: {vector_count} vectors, dimension={dimension}")
                if dimension and dimension != config.PINECONE_EMBEDDING_DIM:
                    logger.error(
                        f"[RAG] ⚠️ DIMENSION MISMATCH: Pinecone index has dim={dimension}, "
                        f"but embedding model produces dim={config.PINECONE_EMBEDDING_DIM}. "
                        f"Queries will fail!"
                    )
            except Exception as stats_err:
                logger.warning(f"[RAG] Could not validate Pinecone index stats: {stats_err}")
        else:
            logger.warning("PINECONE_API_KEY not set. RAG vector upserts/queries disabled.")
    except Exception as e:
        logger.warning(f"Pinecone initialization failed (RAG disabled): {e}")

    # Initialize Neo4j base graph structure
    try:
        from backend.app.services.graph_service import l3_manager
        await l3_manager.initialize_base_graph()
    except Exception as e:
        logger.warning(f"Neo4j base graph initialization failed: {e}")

    # Initialize Session Manager context
    try:
        from backend.app.services.session_manager import SessionManager
        await SessionManager.restore_active_sessions()
        await SessionManager.start_workers()
    except Exception as e:
        logger.warning(f"SessionManager startup failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down MVE...")
    try:
        from backend.app.services.session_manager import SessionManager
        await SessionManager.stop_workers()
    except Exception as e:
        pass
    await db_manager.disconnect()
    
    redis_pool = registry.get("redis")
    if redis_pool:
        await redis_pool.close()
