import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import config
from backend.app.db.mongo import MongoDB
from backend.app.db.database import db_manager
from backend.app.api.ws_routes import router as ws_router
from backend.app.api.routes import router as api_router
from backend.app.core.registry import registry
from backend.app.services.embedding import EmbeddingService
from starlette.middleware.base import BaseHTTPMiddleware
from redis import asyncio as aioredis
import time, os

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
