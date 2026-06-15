import asyncio
import uuid
import logging
import os
import re
import inspect
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from asyncio import QueueEmpty
from collections import OrderedDict
from pymongo import ASCENDING

from backend.app.db.database import db_manager
from backend.app.core.task_registry import TaskRegistry
from backend.app.config import config
from backend.app.models.session_model import Session, Message, SessionSummary
from backend.app.utils.summary_generator import generate_session_summary
from backend.app.core.registry import registry
from backend.app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Helper function for memory prefetch (HOOK 2)
async def _fire_memory_prefetch(session_id: str, message: str):
    """Fire memory prefetch in background - never let this crash the voice pipeline"""
    try:
        from memory import memory_engine
        await memory_engine.on_user_message(session_id, message)
    except Exception:
        pass  # never let this crash the voice pipeline

MAX_HISTORY_MESSAGES = 200
EMBEDDING_CHUNK_SIZE = 20
DEFAULT_SUMMARY_TIMEOUT_SECONDS = float(os.getenv("SESSION_SUMMARY_TIMEOUT_SECONDS", "10"))
DEFAULT_BATCH_INTERVAL_SECONDS = float(os.getenv("SESSION_BATCH_INTERVAL_SECONDS", "5"))
DEFAULT_BATCH_SIZE = int(os.getenv("SESSION_BATCH_SIZE", "10"))
DEFAULT_FINALIZING_FETCH_MULTIPLIER = int(os.getenv("SESSION_FINALIZING_FETCH_MULTIPLIER", "3"))
DEFAULT_RESUME_GRACE_SECONDS = float(os.getenv("SESSION_RESUME_GRACE_SECONDS", "45"))

class SessionManager:
    """
    Manages the lifecycle of user chat sessions.
    Handles creation, message tracking, summarization, and storage.
    """

    # In-memory storage for active sessions
    active_sessions: "OrderedDict[str, Session]" = OrderedDict()
    _end_session_queue: Optional[asyncio.Queue] = None

    _queue_lock: Optional[asyncio.Lock] = None
    _queue_set = set()
    _batch_worker_task: Optional[asyncio.Task] = None
    _worker_running = False

    BATCH_INTERVAL_SECONDS = DEFAULT_BATCH_INTERVAL_SECONDS
    BATCH_SIZE = DEFAULT_BATCH_SIZE
    FINALIZING_FETCH_MULTIPLIER = DEFAULT_FINALIZING_FETCH_MULTIPLIER
    SUMMARY_TIMEOUT_SECONDS = DEFAULT_SUMMARY_TIMEOUT_SECONDS
    RESUME_GRACE_SECONDS = DEFAULT_RESUME_GRACE_SECONDS

    @classmethod
    def _cache_get(cls, session_id: str) -> Optional[Session]:
        cached = cls.active_sessions.get(session_id)
        if cached is None:
            return None
        cls.active_sessions.move_to_end(session_id)
        return cached

    @classmethod
    def _cache_put(cls, session: Session):
        sid = str(session.session_id)
        cls.active_sessions[sid] = session
        cls.active_sessions.move_to_end(sid)
        max_size = max(10, int(getattr(config, "SESSION_LRU_MAX_SIZE", 100)))
        while len(cls.active_sessions) > max_size:
            cls.active_sessions.popitem(last=False)

    @classmethod
    def _cache_delete(cls, session_id: str):
        cls.active_sessions.pop(session_id, None)

    @classmethod
    def _session_to_cache_payload(cls, session: Session) -> Dict[str, Any]:
        return {
            "session_id": session.session_id,
            "name": session.name,
            "pinned": session.pinned,
            "archived": session.archived,
            "priority": session.priority,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_message_at": session.last_message_at,
            "ended_at": session.ended_at,
            "status": session.status,
            "summary": session.summary,
            "keywords": session.keywords,
            "topic": session.topic,
            "tags": session.tags,
            "relevance_score": session.relevance_score,
            "feedback_count": session.feedback_count,
            "chunk_count": session.chunk_count,
            "chunk_embeddings": session.chunk_embeddings,
            "messages": [m.model_dump() for m in session.messages[-MAX_HISTORY_MESSAGES:]],
            "context_tags": session.context_tags,
            "importance_score": session.importance_score,
            "embedding": session.embedding,
        }

    @classmethod
    async def _cache_session_hot(cls, session: Session):
        cls._cache_put(session)
        try:
            await CacheService.set_session_cache(
                str(session.session_id),
                cls._session_to_cache_payload(session),
                ttl_seconds=int(getattr(config, "SESSION_CACHE_TTL_SECONDS", 900)),
            )
        except Exception:
            pass

    @classmethod
    async def _load_hot_cached_session(cls, session_id: str) -> Optional[Session]:
        cached = cls._cache_get(session_id)
        if cached is not None:
            return cached
        payload = await CacheService.get_session_cache(session_id)
        if isinstance(payload, dict) and payload.get("session_id"):
            restored = cls._session_from_doc(payload)
            cls._cache_put(restored)
            return restored
        return None

    @classmethod
    def _dispatch_summary_task(cls, session_id: str) -> bool:
        if not getattr(config, "DISTRIBUTED_TASKS_ENABLED", False):
            return False
        try:
            from backend.app.worker.celery_app import celery_app
            from backend.app.worker.tasks import summarize_session

            if not getattr(celery_app, "available", False):
                return False

            summarize_session.delay(session_id)
            return True
        except Exception as exc:
            logger.warning("Celery dispatch failed for session %s: %s", session_id, exc)
            return False

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        # Create lazily to ensure this runs inside an active event loop.
        if cls._queue_lock is None:
            cls._queue_lock = asyncio.Lock()
        return cls._queue_lock

    @classmethod
    def _get_end_queue(cls) -> asyncio.Queue:
        if cls._end_session_queue is None:
            cls._end_session_queue = asyncio.Queue()
        return cls._end_session_queue

    @classmethod
    async def restore_active_sessions(cls):
        """Restore all active sessions into hot memory on startup."""
        logger.info("Restoring active sessions from MongoDB...")
        try:
            docs = await cls._with_sessions_collection(
                lambda collection: collection.find(
                    {"status": "active"}, 
                    {"_id": 0}
                ).to_list(length=None)
            )
            count = 0
            for doc in (docs or []):
                session = cls._session_from_doc(doc)
                await cls._cache_session_hot(session)
                count += 1
            logger.info("Successfully restored %d active sessions to cache.", count)
        except Exception as e:
            logger.error("Failed to restore active sessions: %s", e)

    @classmethod
    async def start_workers(cls):
        """Start background batch worker for summary finalization."""
        if getattr(config, "DISTRIBUTED_TASKS_ENABLED", False):
            logger.info("Session batch worker disabled (distributed tasks enabled)")
            return

        if cls._worker_running and cls._batch_worker_task and not cls._batch_worker_task.done():
            return

        cls._worker_running = True
        cls._batch_worker_task = TaskRegistry.track(
            cls._batch_processor(),
            name="session_batch_processor",
        )
        logger.info(
            "Session batch worker started (interval=%ss, batch_size=%s)",
            cls.BATCH_INTERVAL_SECONDS,
            cls.BATCH_SIZE,
        )

    @classmethod
    async def stop_workers(cls):
        """Stop background batch worker gracefully."""
        cls._worker_running = False
        task = cls._batch_worker_task
        cls._batch_worker_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Session batch worker stopped")

    @classmethod
    async def _batch_processor(cls):
        """Periodically process finalizing sessions in bounded batches."""
        while cls._worker_running:
            try:
                await asyncio.sleep(cls.BATCH_INTERVAL_SECONDS)

                # First consume locally queued sessions, then backfill from DB to recover
                # sessions that were left in finalizing state after restarts.
                batch = await cls._dequeue_batch(cls.BATCH_SIZE)
                if len(batch) < cls.BATCH_SIZE:
                    remaining = cls.BATCH_SIZE - len(batch)
                    db_batch = await cls._fetch_finalizing_batch(remaining)
                    for sid in db_batch:
                        if sid not in batch:
                            batch.append(sid)

                if not batch:
                    continue

                # Transition queued sessions to finalizing in worker context,
                # never on websocket close path.
                await asyncio.gather(
                    *(cls._ensure_finalizing_status(session_id) for session_id in batch),
                    return_exceptions=True,
                )

                logger.info("Processing session-finalization batch size=%s", len(batch))
                results = await asyncio.gather(
                    *(cls.process_session_summary(session_id) for session_id in batch),
                    return_exceptions=True,
                )
                for session_id, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error("Session finalization failed for %s: %s", session_id, result, exc_info=True)

                await cls._prune_inactive_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Batch processor loop error: %s", e, exc_info=True)

    @classmethod
    async def _prune_inactive_sessions(cls):
        """Drop stale inactive sessions from in-memory map to keep memory bounded."""
        ttl = max(60, int(getattr(config, "ACTIVE_SESSION_TTL_SECONDS", 1200)))
        cutoff = datetime.now(timezone.utc).timestamp() - ttl
        to_remove: List[str] = []
        for sid, session in list(cls.active_sessions.items()):
            if getattr(session, "status", "active") != "active":
                continue
            marker = session.last_message_at or session.updated_at or session.created_at
            if not marker:
                continue
            if marker.tzinfo is None:
                marker = marker.replace(tzinfo=timezone.utc)
            if marker.timestamp() < cutoff:
                to_remove.append(sid)

        for sid in to_remove:
            cls._cache_delete(sid)
        if to_remove:
            logger.info("Pruned %s inactive sessions from memory", len(to_remove))

    @classmethod
    async def _fetch_finalizing_batch(cls, limit: int) -> List[str]:
        """
        Fetch pending sessions directly from MongoDB using indexed status/updated_at.
        """
        if limit <= 0:
            return []

        query_limit = max(limit, limit * cls.FINALIZING_FETCH_MULTIPLIER)

        cutoff = datetime.now(timezone.utc).timestamp() - cls.RESUME_GRACE_SECONDS

        async def _query_ids(collection) -> List[str]:
            cursor = collection.find(
                {
                    "status": {"$in": ["finalizing", "partial_sync", "pending_vector"]},
                    "updated_at": {"$lte": datetime.fromtimestamp(cutoff, tz=timezone.utc)},
                },
                {"session_id": 1, "_id": 0},
            ).sort("updated_at", ASCENDING).limit(query_limit)
            
            raw_docs = []
            if hasattr(cursor, "to_list"):
                # Handle both PyMongo (sync returns list) and Motor (async returns coroutine)
                to_list_result = cursor.to_list(length=query_limit)
                if inspect.isawaitable(to_list_result):
                    raw_docs = await to_list_result
                else:
                    raw_docs = to_list_result
            else:
                raw_docs = list(cursor)
                
            ids = []
            for doc in raw_docs:
                sid = str(doc.get("session_id", "")).strip()
                if sid:
                    ids.append(sid)
            return ids

        ids = await cls._with_sessions_collection(_query_ids)
        if not ids:
            return []
        return ids[:limit]

    @classmethod
    def enqueue_for_finalization(cls, session_id: str) -> bool:
        """
        Non-blocking enqueue used by websocket close path.
        No DB writes are performed here.
        """
        if not session_id:
            return False

        if cls._dispatch_summary_task(session_id):
            return True

        if session_id in cls._queue_set:
            return False

        cls._queue_set.add(session_id)
        cls._get_end_queue().put_nowait(session_id)
        return True

    @classmethod
    async def _dequeue_batch(cls, limit: int) -> List[str]:
        queue = cls._get_end_queue()
        batch: List[str] = []
        for _ in range(limit):
            try:
                sid = queue.get_nowait()
            except QueueEmpty:
                break
            cls._queue_set.discard(sid)
            if sid:
                batch.append(sid)
        return batch

    @classmethod
    async def _remove_from_queue(cls, session_id: str):
        cls._queue_set.discard(session_id)

    @classmethod
    async def start_or_resume_session(cls, requested_session_id: Optional[str] = None) -> str:
        """
        Start a new session or recover an existing active/finalizing session from MongoDB.
        Completed sessions are never resumed.
        """
        if requested_session_id:
            doc = await cls._with_sessions_collection(
                lambda collection: collection.find_one(
                        {"session_id": requested_session_id},
                        {
                            "_id": 0,
                            "session_id": 1,
                            "name": 1,
                            "pinned": 1,
                            "archived": 1,
                            "priority": 1,
                            "created_at": 1,
                            "updated_at": 1,
                            "last_message_at": 1,
                            "ended_at": 1,
                            "status": 1,
                            "summary": 1,
                            "keywords": 1,
                            "topic": 1,
                            "tags": 1,
                            "relevance_score": 1,
                            "feedback_count": 1,
                            "chunk_count": 1,
                            "chunk_embeddings": 1,
                            "messages": {"$slice": -MAX_HISTORY_MESSAGES},
                            "context_tags": 1,
                            "importance_score": 1,
                            "embedding": 1,
                        },
                    )
            )
            if doc:
                status = str(doc.get("status") or "active")
                if status == "completed":
                    cls._cache_delete(requested_session_id)
                    await CacheService.delete_session_cache(requested_session_id)
                    await cls._remove_from_queue(requested_session_id)
                    logger.info("Requested completed session %s; creating a new session", requested_session_id)
                    return await cls._create_new_session()

                # MongoDB is the source of truth for restart recovery.
                recovered = cls._session_from_doc(doc)
                recovered.status = "active"
                recovered.updated_at = datetime.now(timezone.utc)
                await cls._cache_session_hot(recovered)
                await cls._remove_from_queue(requested_session_id)
                await cls._upsert_session_header(requested_session_id, status="active")
                logger.info("Recovered session from MongoDB: %s", requested_session_id)
                return requested_session_id

            if not db_manager.degraded_mode:
                logger.info("Requested session_id not found in MongoDB, creating new session (requested=%s)", requested_session_id)
                return await cls._create_new_session()

            # DB unavailable fallback.
            in_memory = await cls._load_hot_cached_session(requested_session_id)
            if in_memory and in_memory.status != "completed":
                return requested_session_id

            logger.info("Requested session_id not found/resumable, creating new session (requested=%s)", requested_session_id)
            return await cls._create_new_session()

        return await cls._create_new_session()

    @classmethod
    async def _create_new_session(cls, session_id: Optional[str] = None) -> str:
        sid = session_id
        if not sid:
            while True:
                candidate = str(uuid.uuid4())
                existing = await cls._with_sessions_collection(
                    lambda collection: collection.find_one({"session_id": candidate}, {"_id": 1})
                )
                if not existing:
                    sid = candidate
                    break
        
        now = datetime.now(timezone.utc)
        new_session = Session(
            session_id=sid,
            name=None,
            pinned=False,
            archived=False,
            priority=0.5,
            created_at=now,
            updated_at=now,
            last_message_at=now,
            status="active",
            relevance_score=0.5,
        )
        await cls._cache_session_hot(new_session)
        await cls._upsert_session_header(sid, status="active")
        
        # HOOK 1 - Memory context fetch on session start
        try:
            from memory import memory_engine
            # For new sessions, we don't have initial user input yet, so use empty context
            ctx = await memory_engine.get_context_for_session(sid, "", "general")
            # Store memory context in session for later use
            new_session.memory_context = memory_engine.format_context_for_prompt(ctx)
        except Exception as e:
            logging.warning(f"Memory context fetch failed for new session {sid}: {e}")
            new_session.memory_context = ""
        
        logger.info("Started session: %s", sid)
        return sid

    @classmethod
    def start_session(cls) -> str:
        """Backward-compatible local session creation without async recovery."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=session_id,
            name=None,
            pinned=False,
            archived=False,
            priority=0.5,
            created_at=now,
            updated_at=now,
            last_message_at=now,
            status="active",
            relevance_score=0.5,
        )
        cls._cache_put(session)
        logger.info("Started session (legacy path): %s", session_id)
        return session_id

    @classmethod
    async def get_session(cls, session_id: str) -> Optional[Session]:
        cached = cls._cache_get(session_id)
        if cached is not None:
            return cached

        try:
            collection = db_manager.get_collection(config.SESSIONS_COLLECTION)
        except RuntimeError:
            return None

        try:
            doc = await collection.find_one(
                {"session_id": session_id},
                {
                    "_id": 0,
                    "session_id": 1,
                    "name": 1,
                    "pinned": 1,
                    "archived": 1,
                    "priority": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "last_message_at": 1,
                    "ended_at": 1,
                    "status": 1,
                    "summary": 1,
                    "keywords": 1,
                    "topic": 1,
                    "tags": 1,
                    "relevance_score": 1,
                    "feedback_count": 1,
                    "chunk_count": 1,
                    "chunk_embeddings": 1,
                    "messages": {"$slice": -MAX_HISTORY_MESSAGES},
                    "context_tags": 1,
                    "importance_score": 1,
                    "embedding": 1,
                },
            )
        except Exception as e:
            logger.error("[SM] get_session DB call failed: %s", e)
            return None

        if not doc:
            return None
        restored = cls._session_from_doc(doc)
        cls._cache_put(restored)
        return restored

    @classmethod
    async def add_message(cls, session_id: str, role: str, content: str):
        """
        Adds a message to an active session and persists immediately to MongoDB.
        MongoDB is the source of truth; in-memory state is a hot cache.
        """
        now = datetime.now(timezone.utc)
        if cls._cache_get(session_id) is None:
            # Best effort cache reconstruction for late messages on a recovered-but-uncached session.
            cls._cache_put(Session(
                session_id=session_id,
                created_at=now,
                updated_at=now,
                status="active",
            ))

        message = Message(role=role, content=content, timestamp=now)
        session = cls._cache_get(session_id)
        if session is None:
            session = Session(session_id=session_id, created_at=now, updated_at=now, status="active")
            cls._cache_put(session)
        session.status = "active"
        session.updated_at = now
        session.last_message_at = now
        session.messages.append(message)

        # Enforce history limit
        if len(session.messages) > MAX_HISTORY_MESSAGES:
            session.messages = session.messages[-MAX_HISTORY_MESSAGES:]

        persisted = await cls._persist_message(session_id, session, message)
        if not persisted:
            logger.warning("Message persistence failed for session %s", session_id)
        
        # HOOK 2 - Memory prefetch on user message (non-blocking)
        if role == "user":  # Only prefetch on user messages
            import asyncio
            asyncio.create_task(
                _fire_memory_prefetch(session_id, content)
            )
        
        await cls._cache_session_hot(session)

    @classmethod
    async def end_session(cls, session_id: str) -> Optional[Session]:
        """
        Finalizes session by directly running generate_session_summary and updating MongoDB/Pinecone.
        """
        session = cls._cache_get(session_id)
        now = datetime.now(timezone.utc)
        
        if not session:
            session = await cls.get_session(session_id)
            if not session:
                logger.warning("Session %s not found for finalization", session_id)
                return None

        session.ended_at = now
        session.status = "completed"
        session.updated_at = now
        
        await cls._upsert_session_header(session_id, status="completed", ended_at=now)
        
        messages_for_summary = [{"role": m.role, "content": m.content} for m in session.messages]

        if messages_for_summary is not None and len(messages_for_summary) > 0:
            try:
                session_summary_obj = await generate_session_summary(messages_for_summary)
                summary_text = session_summary_obj.summary
                session.keywords = session_summary_obj.keywords
                session.context_tags = session_summary_obj.context_tags
            except Exception as e:
                logger.warning(f"Summary generation skipped (Rate Limit/429): {e}")
                summary_text = f"Session with {len(messages_for_summary)} messages."
                session.keywords = []
                session.context_tags = []
                
            if summary_text and len(summary_text) > 0:
                session.summary = summary_text
            else:
                session.summary = f"Session with {len(messages_for_summary)} messages."
                summary_text = session.summary
                
            logger.info(f"[MEMORY] Summary generated for session {session_id}")

            try:
                # Embedding Integration
                embedding = None
                embedding_service = registry.get("embedding")
                if embedding_service:
                    try:
                        embedding = await embedding_service.embed_async(summary_text)
                        session.embedding = embedding
                        logger.info(f"[MEMORY] Embedding created for session {session_id}")
                    except Exception as embed_err:
                        logger.error(f"[MEMORY] Embedding failed: {embed_err}")
                
                topic = ", ".join(session.keywords[:2]) if session.keywords else None
                tags = session.context_tags
                
                chunk_embeddings = await cls._build_chunk_embeddings(session_id, messages_for_summary, topic, tags)
                
                msg_count = len(session.messages) if session.messages is not None else 0
                msg_score = min(msg_count / 20.0, 1.0)
                created_at = session.created_at or now
                if getattr(created_at, "tzinfo", None) is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                days_old = max(0.0, (now - created_at).total_seconds() / 86400.0)
                recency_score = 1.0 / (1.0 + days_old)
                pin_boost = 1.5 if getattr(session, "pinned", False) else 1.0
                importance_score = (0.4 * msg_score + 0.4 * recency_score) * pin_boost
                
                summary_hash = hashlib.sha256(summary_text.strip().lower().encode()).hexdigest()
                
                session.topic = topic
                session.tags = tags
                session.chunk_embeddings = chunk_embeddings
                session.chunk_count = len(chunk_embeddings)
                session.importance_score = importance_score

                # ── Atomic 3-phase sync via MemorySaga ──────────────────
                # The Saga writes to MongoDB outbox first (commit point),
                # then coordinates Pinecone + Neo4j with automatic retry.
                from memory.memory_saga import MemorySaga

                saga = MemorySaga(
                    session_id=session_id,
                    summary=summary_text,
                    embedding=embedding or [],
                    raw_segment="",
                    source="end_session",
                )
                saga_ok = await saga.execute()

                final_status = "completed" if saga_ok else "partial_sync"
                
                # Update MongoDB session header with enriched metadata
                await cls._with_sessions_collection(
                    lambda collection: collection.update_one(
                        {"session_id": session_id},
                        {"$set": {
                            "summary": summary_text,
                            "embedding": embedding,
                            "status": final_status,
                            "keywords": session.keywords,
                            "context_tags": session.context_tags,
                            "topic": topic,
                            "tags": tags,
                            "chunk_embeddings": chunk_embeddings,
                            "chunk_count": session.chunk_count,
                            "summary_hash": summary_hash,
                            "importance_score": importance_score
                        }}
                    )
                )
            except Exception as e:
                logger.error("Embedding/Upsert failed for session %s: %s", session_id, e)
        
        # HOOK 3 - Memory save on session end (before cleanup)
        try:
            from memory import memory_engine
            messages = [{"role": m.role, "content": str(m.content)} 
                        for m in session.messages]
            await memory_engine.save_session(
                session_id=session_id,
                workflow_type=getattr(session, "workflow_type", "general"),
                messages=messages,
                start_time=session.created_at.isoformat() if session.created_at else datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.error(f"Memory save failed for session {session_id}: {e}")
        
        cls._cache_delete(session_id)
        try:
            await CacheService.delete_session_cache(session_id)
        except Exception:
            pass
            
        return session

    @classmethod
    async def mark_finalizing_and_enqueue(cls, session_id: str):
        """
        Background-only transition to finalizing followed by enqueue.
        Intended for deferred close handling where close path must stay non-blocking.
        """
        now = datetime.now(timezone.utc)
        session = cls._cache_get(session_id)
        if session:
            session.ended_at = now
            session.status = "finalizing"
            session.updated_at = now
        await cls._upsert_session_header(session_id, status="finalizing", ended_at=now)
        if not cls._dispatch_summary_task(session_id):
            cls.enqueue_for_finalization(session_id)

    @classmethod
    async def process_session_summary(cls, session_id: str):
        """
        Fetch session from MongoDB, summarize, embed, persist results, and mark complete.
        """
        doc = await cls._with_sessions_collection(
            lambda collection: collection.find_one(
                {"session_id": session_id, "status": {"$in": ["active", "finalizing", "partial_sync", "completed", "pending_vector"]}},
                {
                    "_id": 0,
                    "session_id": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "last_message_at": 1,
                    "relevance_score": 1,
                    "messages": 1,
                },
            )
        )
        if not doc:
            logger.warning("Session %s not found in MongoDB during finalization", session_id)
            return

        messages = cls._normalize_messages(doc.get("messages", []))
        if not messages:
            await cls._mark_completed(
                session_id,
                summary="Session ended with no messages.",
                embedding=[],
                topic=None,
                tags=[],
                chunk_embeddings=[],
                chunk_count=0,
                last_message_at=doc.get("last_message_at") or datetime.now(timezone.utc),
            )
            cls._cache_delete(session_id)
            await CacheService.delete_session_cache(session_id)




            return

        cache_marker = str(doc.get("last_message_at") or doc.get("updated_at") or "")
        summary_cache_key = f"summary_obj:{session_id}:{cache_marker}"
        
        cached_summary = await CacheService.get_json(summary_cache_key)
        if isinstance(cached_summary, dict) and "summary" in cached_summary:
            summary_obj = SessionSummary(**cached_summary)
        else:
            summary_obj = await cls._generate_summary_with_timeout(session_id, messages)
            await CacheService.set_json(summary_cache_key, getattr(summary_obj, "dict", lambda: summary_obj.model_dump())(), ttl_seconds=config.CACHE_TTL_SECONDS)

        summary_text = summary_obj.summary
        topic = ", ".join(summary_obj.keywords[:2]) if summary_obj.keywords else None
        tags = summary_obj.context_tags

        chunk_embeddings = await cls._build_chunk_embeddings(session_id, messages, topic, tags)

        msg_count = len(messages) if messages is not None else 0
        msg_score = min(msg_count / 20.0, 1.0)
        created_at = doc.get("created_at") or datetime.now(timezone.utc)
        if getattr(created_at, "tzinfo", None) is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        days_old = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 86400.0)
        recency_score = 1.0 / (1.0 + days_old)
        pin_boost = 1.5 if doc.get("pinned") else 1.0
        importance_score = (0.4 * msg_score + 0.4 * recency_score) * pin_boost

        summary_hash = hashlib.sha256(summary_text.strip().lower().encode()).hexdigest()

        embedding = None
        existing_doc = await cls._with_sessions_collection(
            lambda collection: collection.find_one({"summary_hash": summary_hash}, {"embedding": 1})
        )
        if existing_doc and existing_doc.get("embedding"):
            embedding = existing_doc["embedding"]
            logger.info("Found existing embedding for summary hash in session %s", session_id)
        else:
            try:
                embedding_service = registry.get("embedding")
                embedding = await asyncio.to_thread(embedding_service.embed, summary_text)
            except Exception as e:
                logger.error("Embedding generation failed for session %s: %s", session_id, e, exc_info=True)

        # Entity extraction / Pinecone / Neo4j writes happen per-turn via
        # memory_engine.save_session() (supervisor_graph's save_session node).
        # MongoDB bookkeeping here just finalizes this SessionManager row.
        await cls._mark_completed(
            session_id,
            summary=summary_text,
            embedding=embedding or [],
            topic=topic,
            tags=tags,
            chunk_embeddings=chunk_embeddings,
            chunk_count=len(chunk_embeddings),
            last_message_at=doc.get("last_message_at") or doc.get("updated_at") or datetime.now(timezone.utc),
            importance_score=importance_score,
            summary_hash=summary_hash,
            status="completed"
        )

    @classmethod
    async def _generate_summary_with_timeout(cls, session_id: str, messages: List[Dict[str, str]]) -> SessionSummary:
        if not messages:
            return SessionSummary(
                summary="Session ended with no meaningful content.",
                keywords=[],
                context_tags=[]
            )

        try:
            summary_obj = await asyncio.wait_for(
                generate_session_summary(messages),
                timeout=cls.SUMMARY_TIMEOUT_SECONDS,
            )
            return summary_obj
        except asyncio.TimeoutError:
            logger.warning("Summary timeout for session %s", session_id)
        except Exception as e:
            logger.error("Summary generation failed for session %s: %s", session_id, e, exc_info=True)

        return SessionSummary(
            summary=cls._fallback_summary(messages),
            keywords=[],
            context_tags=[]
        )

    @classmethod
    def _fallback_summary(cls, messages: List[Dict[str, str]]) -> str:
        snippets = [m.get("content", "")[:80] for m in messages[-3:] if m.get("content")]
        if snippets:
            return f"Session with {len(messages)} messages. Recent topics: {' | '.join(snippets)}"
        return f"Session with {len(messages)} messages."

    @classmethod
    async def _persist_message(cls, session_id: str, session: Session, message: Message) -> bool:
        now = datetime.now(timezone.utc)
        created_at = session.created_at if isinstance(session.created_at, datetime) else now
        update = {
            "$setOnInsert": {
                "session_id": session_id,
                "created_at": created_at,
                "name": session.name,
                "pinned": bool(getattr(session, "pinned", False)),
                "archived": bool(getattr(session, "archived", False)),
                "priority": float(getattr(session, "priority", 0.5)),
                "summary": session.summary,
                "embedding": session.embedding or [],
                "topic": session.topic,
                "tags": session.tags,
                "relevance_score": session.relevance_score,
            },
            "$set": {
                "updated_at": now,
                "last_message_at": now,
                "status": "active",
            },
            "$push": {
                "messages": message.model_dump()
            },
        }

        try:
            result = await cls._with_sessions_collection(
                lambda collection: collection.update_one(
                    {"session_id": session_id},
                    update,
                    True,
                )
            )
            if result is None:
                logger.warning("Session persistence degraded for %s; keeping in-memory state", session_id)
                return False
            logger.info("Message persisted for session %s (role=%s)", session_id, message.role)
            return True
        except Exception as e:
            logger.error("Failed to persist message for session %s: %s", session_id, e, exc_info=True)
            return False

    @classmethod
    async def _upsert_session_header(
        cls,
        session_id: str,
        status: str,
        ended_at: Optional[datetime] = None,
    ):
        now = datetime.now(timezone.utc)
        set_fields: Dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if ended_at is not None:
            set_fields["ended_at"] = ended_at

        result = await cls._with_sessions_collection(
            lambda collection: collection.update_one(
                {"session_id": session_id},
                {
                    "$set": set_fields,
                    "$setOnInsert": {
                        "session_id": session_id,
                        "created_at": now,
                        "name": None,
                        "pinned": False,
                        "archived": False,
                        "priority": 0.5,
                        "last_message_at": now,
                        "messages": [],
                        "summary": None,
                        "embedding": [],
                        "topic": None,
                        "tags": [],
                        "relevance_score": 0.5,
                        "feedback_count": 0,
                        "chunk_embeddings": [],
                        "chunk_count": 0,
                    },
                },
                True,
            )
        )
        if result is None:
            logger.warning("Header upsert degraded for session %s", session_id)

        hot = cls._cache_get(session_id)
        if hot is not None:
            hot.status = status
            hot.updated_at = now
            if ended_at is not None:
                hot.ended_at = ended_at
            await cls._cache_session_hot(hot)

    @classmethod
    async def _mark_completed(
        cls,
        session_id: str,
        summary: str,
        embedding: List[float],
        topic: Optional[str],
        tags: List[str],
        chunk_embeddings: List[List[float]],
        chunk_count: int,
        last_message_at: datetime,
        importance_score: Optional[float] = None,
        summary_hash: Optional[str] = None,
        status: str = "completed"
    ):
        if not summary or not summary.strip():
            summary = "No summary available"

        now = datetime.now(timezone.utc)

        set_fields = {
            "summary": summary,
            "embedding": embedding,
            "topic": topic,
            "tags": tags,
            "keywords": tags,
            "chunk_embeddings": chunk_embeddings,
            "chunk_count": chunk_count,
            "status": status,
            "updated_at": now,
            "last_message_at": last_message_at,
            "ended_at": now,
        }
        if importance_score is not None:
            set_fields["importance_score"] = importance_score
        if summary_hash is not None:
            set_fields["summary_hash"] = summary_hash
            
        result = await cls._with_sessions_collection(
            lambda collection: collection.update_one(
                {"session_id": session_id},
                {"$set": set_fields},
                upsert=True
            )
        )
        if result is None:
            logger.warning("Completion persistence degraded for session %s", session_id)
            return

        await CacheService.delete_session_cache(session_id)





    @classmethod
    def _extract_topic_and_tags(cls, summary: str, messages: List[Dict[str, str]]) -> Tuple[Optional[str], List[str]]:
        text = f"{summary} " + " ".join(m.get("content", "") for m in messages)
        tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
        stop = {
            "the", "and", "for", "with", "that", "this", "from", "have", "about", "your", "you", "are",
            "was", "were", "what", "when", "where", "will", "would", "could", "should", "into", "over",
        }
        counts: Dict[str, int] = {}
        for token in tokens:
            if token in stop:
                continue
            counts[token] = counts.get(token, 0) + 1

        if not counts:
            return None, []

        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        tags = [word for word, _ in ranked[:8]]
        topic = tags[0] if tags else None
        return topic, tags

    @classmethod
    async def _build_chunk_embeddings(
        cls,
        session_id: str,
        messages: List[Dict[str, str]],
        topic: Optional[str],
        tags: List[str],
    ) -> List[List[float]]:
        chunks: List[List[Dict[str, str]]] = [
            messages[i:i + EMBEDDING_CHUNK_SIZE]
            for i in range(0, len(messages), EMBEDDING_CHUNK_SIZE)
        ]

        chunk_vectors: List[List[float]] = []
        for idx, chunk in enumerate(chunks):
            chunk_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in chunk
            )
            if not chunk_text.strip():
                continue
            try:
                embedding_service = registry.get("embedding")
                vector = await asyncio.to_thread(embedding_service.embed, chunk_text)
                if vector:
                    chunk_vectors.append(vector)
                    # Store each chunk separately for long-session recall.
                    chunk_id = f"{session_id}::chunk::{idx}"
                    metadata = {
                        "session_id": session_id,
                        "chunk_index": idx,
                        "topic": topic if topic is not None else "general",
                        "tags": tags if tags is not None and len(tags) > 0 else ["unknown"],
                        "message_count": len(chunk) if chunk is not None else 0,
                    }
                    vector_search = registry.get("vector")
                    await vector_search.upsert(chunk_id, vector, metadata)
                    logger.info(f"[RAG] Pinecone chunk upsert success: {chunk_id}")
            except Exception as exc:
                logger.warning("[RAG] Chunk embedding/upsert failed for %s[%s]: %s", session_id, idx, exc)

        return chunk_vectors

    @classmethod
    async def _ensure_finalizing_status(cls, session_id: str):
        try:
            collection = db_manager.get_collection(config.SESSIONS_COLLECTION)
        except RuntimeError:
            return

        try:
            doc = await collection.find_one(
                {"session_id": session_id},
                {"_id": 0, "status": 1},
            )
        except Exception as e:
            logger.error("[SM] _ensure_finalizing_status DB failed: %s", e)
            return
        if not doc:
            return

        status = str(doc.get("status") or "active")
        if status == "completed":
            return

        await cls._upsert_session_header(
            session_id,
            status="finalizing",
            ended_at=datetime.now(timezone.utc),
        )

    @classmethod
    def _validate_session_data(cls, doc: Dict[str, Any]):
        assert "messages" in doc, "Document requires 'messages' field"
        assert isinstance(doc["messages"], list), "'messages' must be a list"

    @classmethod
    def _session_from_doc(cls, doc: Dict[str, Any]) -> Session:
        cls._validate_session_data(doc)
        raw_messages = doc.get("messages", []) or []
        messages: List[Message] = []
        for msg in raw_messages[-MAX_HISTORY_MESSAGES:]:
            if isinstance(msg, dict):
                try:
                    messages.append(Message(**msg))
                except Exception:
                    role = str(msg.get("role", ""))
                    content = str(msg.get("content", ""))
                    if content:
                        messages.append(Message(role=role, content=content))

        created_at = doc.get("created_at") or datetime.now(timezone.utc)
        updated_at = doc.get("updated_at") or created_at
        last_message_at = doc.get("last_message_at") or updated_at
        ended_at = doc.get("ended_at")

        return Session(
            session_id=str(doc.get("session_id")),
            name=doc.get("name"),
            pinned=bool(doc.get("pinned", False)),
            archived=bool(doc.get("archived", False)),
            priority=float(doc.get("priority", 0.5)),
            created_at=created_at,
            updated_at=updated_at,
            last_message_at=last_message_at,
            ended_at=ended_at,
            status=str(doc.get("status") or "active"),
            summary=doc.get("summary"),
            keywords=doc.get("keywords", []),
            topic=doc.get("topic"),
            tags=doc.get("tags", []),
            messages=messages,
            context_tags=doc.get("context_tags", []),
            importance_score=doc.get("importance_score"),
            relevance_score=float(doc.get("relevance_score", 0.5)),
            feedback_count=int(doc.get("feedback_count", 0)),
            chunk_count=int(doc.get("chunk_count", 0)),
            chunk_embeddings=doc.get("chunk_embeddings", []),
            embedding=doc.get("embedding") or [],
        )

    @classmethod
    def _normalize_messages(cls, messages: List[Any]) -> List[Dict[str, str]]:
        normalized = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "")).strip()
            content = str(msg.get("content", "")).strip()
            if content:
                normalized.append({"role": role, "content": content})
        return normalized

    @classmethod
    async def _safe_db_call(cls, fn):
        """Execute a DB operation safely via db_manager."""
        try:
            result = fn()
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            logger.error("[SM] _safe_db_call failed: %s", e)
            return None

    @classmethod
    async def _with_sessions_collection(cls, fn):
        """Run async collection operations via the unified db_manager."""
        return await db_manager.with_collection(config.SESSIONS_COLLECTION, fn)

    @classmethod
    async def list_sessions(cls, include_archived: bool = False, limit: int = 100) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if not include_archived:
            query["archived"] = {"$ne": True}

        async def _op(collection):
            cursor = collection.find(
                query,
                {
                    "_id": 0,
                    "session_id": 1,
                    "name": 1,
                    "pinned": 1,
                    "archived": 1,
                    "priority": 1,
                    "status": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "last_message_at": 1,
                },
            ).sort([("pinned", -1), ("updated_at", -1)]).limit(max(1, int(limit)))
            if hasattr(cursor, "to_list"):
                result = cursor.to_list(length=max(1, int(limit)))
                if inspect.isawaitable(result):
                    return await result
                return result
            return list(cursor)

        docs = await cls._with_sessions_collection(_op)
        if docs is None:
            return []

        for doc in docs:
            doc["pinned"] = bool(doc.get("pinned", False))
            doc["archived"] = bool(doc.get("archived", False))
            doc["priority"] = float(doc.get("priority", 0.5))
        return docs

    @classmethod
    async def update_session_controls(cls, session_id: str, updates: Dict[str, Any]) -> bool:
        if not session_id or not updates:
            return False

        allowed: Dict[str, Any] = {}
        if "name" in updates:
            name = updates.get("name")
            allowed["name"] = str(name).strip() if name is not None else None
        if "pinned" in updates:
            allowed["pinned"] = bool(updates.get("pinned"))
        if "archived" in updates:
            allowed["archived"] = bool(updates.get("archived"))
        if "priority" in updates:
            try:
                allowed["priority"] = max(0.0, min(1.0, float(updates.get("priority"))))
            except Exception:
                allowed["priority"] = 0.5
        if "relevance_score" in updates:
            try:
                allowed["relevance_score"] = max(0.0, min(1.0, float(updates.get("relevance_score"))))
            except Exception:
                allowed["relevance_score"] = 0.5
        if "feedback_notes" in updates:
            allowed["feedback_notes"] = str(updates.get("feedback_notes") or "").strip()

        if not allowed:
            return False

        allowed["updated_at"] = datetime.now(timezone.utc)
        result = await cls._with_sessions_collection(
            lambda collection: collection.update_one({"session_id": session_id}, {"$set": allowed}, upsert=False)
        )
        if result is None:
            return False

        session = cls._cache_get(session_id)
        if session:
            for key, value in allowed.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            await cls._cache_session_hot(session)
        return bool(getattr(result, "matched_count", 0))

    @classmethod
    async def delete_session(cls, session_id: str) -> bool:
        result = await cls._with_sessions_collection(lambda collection: collection.delete_one({"session_id": session_id}))
        cls._cache_delete(session_id)
        await CacheService.delete_session_cache(session_id)




        await cls._remove_from_queue(session_id)
        if result is None:
            return False
        return bool(getattr(result, "deleted_count", 0))

    @classmethod
    async def fetch_context_sessions(cls, session_ids: List[str]) -> List[Dict[str, Any]]:
        if not session_ids:
            return []

        clean_ids = [str(s).strip() for s in session_ids if str(s).strip()]
        if not clean_ids:
            return []

        async def _op(collection):
            cursor = collection.find(
                {"session_id": {"$in": clean_ids}, "archived": {"$ne": True}},
                {
                    "_id": 0,
                    "session_id": 1,
                    "name": 1,
                    "summary": 1,
                    "messages": {"$slice": -20},
                    "keywords": 1,
                    "topic": 1,
                    "tags": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "last_message_at": 1,
                    "relevance_score": 1,
                    "priority": 1,
                },
            )
            if hasattr(cursor, "to_list"):
                result = cursor.to_list(length=max(1, len(clean_ids)))
                if inspect.isawaitable(result):
                    return await result
                return result
            return list(cursor)

        docs = await cls._with_sessions_collection(_op)
        if docs is None:
            return []

        order = {sid: idx for idx, sid in enumerate(clean_ids)}
        docs.sort(key=lambda d: order.get(str(d.get("session_id")), 10_000))
        return docs

    @classmethod
    async def search_sessions_regex(cls, query: str, limit: int = 5) -> List[Dict]:
        """Basic keyword search for admin/fallback."""
        try:
            collection = db_manager.get_collection(config.SESSIONS_COLLECTION)
        except RuntimeError:
            return []

        try:
            regex = {"$regex": query, "$options": "i"}
            cursor = collection.find({
                "$or": [
                    {"summary": regex},
                    {"keywords": regex},
                    {"context_tags": regex}
                ]
            }).sort("created_at", -1).limit(limit)

            results = await cursor.to_list(length=limit)
            for r in results:
                r["_id"] = str(r["_id"])
            return results
        except Exception as e:
            logger.error(f"Regex search failed: {e}")
            return []
