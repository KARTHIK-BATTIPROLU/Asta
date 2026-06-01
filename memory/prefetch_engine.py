"""
ASTA Memory Layer - L1.5 Speculative Pre-fetch Engine
────────────────────────────────────────────────────

This is the "L1.5" layer - speculative pre-fetching that makes memory feel instant.
When an entity is mentioned mid-session, this fires a background task that 
retrieves all context for that entity and loads it into Redis BEFORE it's needed.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

class PrefetchEngine:
    """
    Speculative pre-fetch engine for entity context.
    
    When entities are spotted in user messages, this engine:
    1. Checks if context is already cached in L1
    2. If not, queues a background fetch from L2→L3→L4
    3. Stores result in L1 for instant access later
    """
    
    def __init__(self):
        self._known_entities: List[str] = []
        self._prefetch_queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._max_queue_size = 50  # Prevent memory leak
        
        # Import here to avoid circular imports
        self._l1_cache = None
        self._l2_graph = None
        self._l3_vectors = None
        self._l4_store = None
        self._entity_extractor = None
    
    def _import_dependencies(self):
        """Lazy import to avoid circular dependencies."""
        if self._l1_cache is None:
            from memory.l1_cache import l1_cache
            from memory.l2_graph import l2_graph
            from memory.l3_vectors import l3_vectors
            from memory.l4_store import l4_store
            from memory.entity_extractor import entity_extractor
            
            self._l1_cache = l1_cache
            self._l2_graph = l2_graph
            self._l3_vectors = l3_vectors
            self._l4_store = l4_store
            self._entity_extractor = entity_extractor
    
    async def start(self) -> None:
        """Call this on app startup."""
        if not settings.MEMORY_PREFETCH_ENABLED:
            logger.info("Prefetch engine disabled by config")
            return
        
        self._import_dependencies()
        
        # Initialize bounded queue to prevent memory leak
        self._prefetch_queue = asyncio.Queue(maxsize=self._max_queue_size)
        
        # Load all known entity names from Neo4j for fast spotting
        try:
            self._known_entities = await self._l2_graph.get_all_entity_names()
        except Exception as e:
            logger.error(f"Failed to load known entities: {e}")
            self._known_entities = []
        
        # Start background worker
        self._worker_task = asyncio.create_task(self._prefetch_worker())
        
        logger.info(f"Prefetch engine started. Known entities: {len(self._known_entities)}")
    
    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Prefetch engine stopped")
    
    async def on_message(self, session_id: str, text: str) -> None:
        """
        Call this on every user message, non-blocking.
        Spots entities in text, queues prefetch for any not already cached.
        
        Args:
            session_id: Current session ID
            text: User message text
        """
        if not settings.MEMORY_PREFETCH_ENABLED or not self._prefetch_queue:
            return
        
        try:
            self._import_dependencies()
            
            # Spot entities in the text
            spotted = self._entity_extractor.spot_entities_in_text(text, self._known_entities)
            
            for entity_name in spotted:
                # Check L1 cache first - don't re-fetch if already cached
                cached = await self._l1_cache.get_entity_context(entity_name)
                
                if not cached:
                    # Queue for prefetch - use put_nowait to avoid blocking
                    # If queue is full, skip this prefetch (backpressure)
                    try:
                        self._prefetch_queue.put_nowait({
                            "entity_name": entity_name,
                            "session_id": session_id,
                            "queued_at": datetime.utcnow().isoformat()
                        })
                    except asyncio.QueueFull:
                        logger.warning(f"Prefetch queue full, skipping entity: {entity_name}")
                        continue
                
                # Always add to session's entity tracking
                await self._l1_cache.add_entity_to_session(session_id, entity_name)
            
            if spotted:
                logger.debug(f"Spotted entities in message: {spotted}")
                
        except Exception as e:
            logger.error(f"Error in prefetch on_message: {e}")
    
    async def _prefetch_worker(self) -> None:
        """Background worker that processes the prefetch queue."""
        logger.info("Prefetch worker started")
        
        while True:
            try:
                # Get next item from queue
                item = await self._prefetch_queue.get()
                entity_name = item["entity_name"]
                
                logger.debug(f"Prefetching context for entity: {entity_name}")
                
                # Step 1: Neo4j cluster search for this entity
                session_ids = await self._l2_graph.get_cluster_session_ids(
                    [entity_name], 
                    depth=settings.MEMORY_CLUSTER_DEPTH
                )
                
                if not session_ids:
                    logger.debug(f"No cluster sessions found for {entity_name}")
                    self._prefetch_queue.task_done()
                    continue
                
                # Step 2: Pinecone vector search within those sessions
                vector_results = await self._l3_vectors.search_by_text(
                    entity_name,
                    top_k=settings.MEMORY_TOP_K_SESSIONS,
                    filter_session_ids=session_ids
                )
                
                if not vector_results:
                    logger.debug(f"No vector results found for {entity_name}")
                    self._prefetch_queue.task_done()
                    continue
                
                # Step 3: Fetch full summaries from MongoDB
                top_ids = [r["session_id"] for r in vector_results]
                full_sessions = await self._l4_store.get_sessions_by_ids(top_ids)
                
                if full_sessions:
                    # Step 4: Cache in Redis
                    await self._l1_cache.cache_entity_context(entity_name, full_sessions)
                    logger.info(f"Prefetched context for '{entity_name}': {len(full_sessions)} sessions")
                
                self._prefetch_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Prefetch worker cancelled")
                break
                
            except Exception as e:
                logger.error(f"Prefetch worker error: {e}")
                # Don't crash the worker - continue processing queue
                try:
                    self._prefetch_queue.task_done()
                except:
                    pass
                await asyncio.sleep(0.1)
    
    async def refresh_known_entities(self) -> None:
        """Call after saving a new session to update the known entities list."""
        if not settings.MEMORY_PREFETCH_ENABLED:
            return
        
        try:
            self._import_dependencies()
            self._known_entities = await self._l2_graph.get_all_entity_names()
            logger.debug(f"Refreshed known entities: {len(self._known_entities)}")
            
        except Exception as e:
            logger.error(f"Failed to refresh known entities: {e}")
    
    def get_queue_size(self) -> int:
        """Get current prefetch queue size for monitoring."""
        if self._prefetch_queue:
            return self._prefetch_queue.qsize()
        return 0

# Export singleton
prefetch_engine = PrefetchEngine()