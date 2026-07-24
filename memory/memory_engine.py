"""
ASTA Memory Layer - Master Memory Engine
──────────────────────────────────────

This is the master orchestrator for all memory operations.
It is the ONLY file that other parts of the app should import from the memory layer.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4
from memory.l1_cache import l1_cache
from memory.l2_graph import l2_graph
from memory.l3_vectors import l3_vectors
from memory.l4_store import l4_store
from memory.entity_extractor import entity_extractor
from memory.prefetch_engine import prefetch_engine
from memory.schema import SessionMetadata, Entity
from backend.app.config import settings

logger = logging.getLogger(__name__)

class MemoryEngine:
    """
    Master orchestrator for all memory operations.
    
    Coordinates the 5-layer memory architecture:
    L0  In-flight context (LangGraph state)
    L1  Redis hot cache (entities + session context)
    L1.5 Speculative prefetch (background entity loading)
    L2  Neo4j knowledge graph (entity clusters + relationships)
    L3  Pinecone vector store (semantic search)
    L4  MongoDB cold store (full sessions + permanent memory)
    """
    
    # ═══ STARTUP / SHUTDOWN ════════════════════════════════════════════════
    
    async def connect_all(self) -> Dict[str, str]:
        """Connect all layers. Called once at app startup."""
        results = {}
        
        # Connect each layer
        layers = [
            ("L1_redis", l1_cache),
            ("L2_neo4j", l2_graph),
            ("L3_pinecone", l3_vectors),
            ("L4_mongodb", l4_store),
        ]
        
        for name, layer in layers:
            try:
                await layer.connect()
                results[name] = "connected"
                logger.info(f"Memory layer {name}: connected")
            except Exception as e:
                results[name] = f"FAILED: {e}"
                logger.error(f"Memory layer {name} failed to connect: {e}")
        
        # Start prefetch engine after all layers are up
        try:
            await prefetch_engine.start()
            results["prefetch_engine"] = "started"
        except Exception as e:
            results["prefetch_engine"] = f"FAILED: {e}"
            logger.error(f"Prefetch engine failed to start: {e}")
        
        logger.info(f"Memory layers status: {results}")
        return results
    
    async def disconnect_all(self) -> None:
        """Graceful shutdown."""
        try:
            await prefetch_engine.stop()
            await l1_cache.disconnect()
            await l2_graph.disconnect()
            # Pinecone and MongoDB connections are managed by their clients
            logger.info("Memory layers disconnected")
        except Exception as e:
            logger.error(f"Error during memory shutdown: {e}")
    
    # ═══ SESSION START — RETRIEVE CONTEXT ══════════════════════════════════
    
    async def get_context_for_session(self, session_id: str, user_input: str, 
                                     workflow_type: str) -> Dict:
        """
        Called at the START of every session or conversation turn.
        Returns context to inject into the LLM system prompt.
        
        Pipeline:
        1. Check L1 cache for already-retrieved context (repeat turns in same session)
        2. Spot entities in user_input
        3. For each entity: check L1 entity cache (may have been pre-fetched)
        4. For uncached entities: L2 cluster search → L3 vector search → L4 fetch
        5. Merge all context, deduplicate by session_id
        6. Cache result in L1 for this session
        7. Fire prefetch for any entities not yet cached
        
        Returns:
            Dict with "sessions", "from_cache", "entities_spotted"
        """
        try:
            # Step 1: Check if we already retrieved context for this session
            cached = await l1_cache.get_retrieved_context(session_id)
            if cached:
                logger.info(f"Retrieved context from L1 cache for session {session_id}")
                return {"sessions": cached, "from_cache": True}
            
            # Step 2: Spot entities in input (fast, no LLM)
            known_entities = await l2_graph.get_all_entity_names()
            spotted = entity_extractor.spot_entities_in_text(user_input, known_entities)
            
            # Step 3: Also check Neo4j for current focus (what was last worked on)
            current_focus = await l2_graph.get_current_focus()
            if current_focus.get("current_focus"):
                focus_entity = current_focus["current_focus"]
                if focus_entity not in spotted:
                    spotted.append(focus_entity)
            
            all_sessions = []
            seen_ids = set()
            
            # Step 4: For each entity, get context with per-entity error handling
            for entity_name in spotted[:5]:  # Cap at 5 entities max
                
                try:
                    # Try L1 cache first
                    entity_ctx = await l1_cache.get_entity_context(entity_name)
                    
                    if entity_ctx:
                        # Use cached context
                        for s in entity_ctx.get("related_sessions", []):
                            key = s.get("turn_id") or s.get("session_id")
                            if key not in seen_ids:
                                all_sessions.append(s)
                                seen_ids.add(key)
                    else:
                        # Full retrieval pipeline with per-layer fallback
                        cluster_ids = []
                        try:
                            cluster_ids = await l2_graph.get_cluster_session_ids(
                                [entity_name], 
                                depth=settings.MEMORY_CLUSTER_DEPTH
                            )
                        except Exception as l2_err:
                            logger.warning(f"L2 cluster search failed for {entity_name}: {l2_err}")
                            # Fall through to L3 without cluster filter
                        
                        if cluster_ids:
                            try:
                                vector_results = await l3_vectors.search_by_text(
                                    user_input,
                                    top_k=settings.MEMORY_TOP_K_SESSIONS,
                                    filter_session_ids=cluster_ids
                                )
                                
                                if vector_results:
                                    try:
                                        full = await l4_store.get_sessions_by_ids(
                                            [r["session_id"] for r in vector_results]
                                        )
                                        
                                        for s in full:
                                            key = s.get("turn_id") or s.get("session_id")
                                            if key not in seen_ids:
                                                all_sessions.append(s)
                                                seen_ids.add(key)
                                    except Exception as l4_err:
                                        logger.warning(f"L4 fetch failed for {entity_name}: {l4_err}")
                            except Exception as l3_err:
                                logger.warning(f"L3 vector search failed for {entity_name}: {l3_err}")
                except Exception as entity_err:
                    logger.error(f"Entity context retrieval failed for {entity_name}: {entity_err}")
                    # Continue with next entity
            
            # If no entities spotted: fall back to general recent session search
            if not all_sessions:
                vector_results = await l3_vectors.search_by_text(
                    user_input, 
                    top_k=settings.MEMORY_TOP_K_SESSIONS
                )
                
                if vector_results:
                    all_sessions = await l4_store.get_sessions_by_ids(
                        [r["session_id"] for r in vector_results]
                    )
            
            # Limit to top-K
            final = all_sessions[:settings.MEMORY_TOP_K_SESSIONS]
            
            # Cache for this session
            await l1_cache.cache_retrieved_context(session_id, final)
            
            # Start session tracking in L1
            await l1_cache.start_session(session_id, workflow_type)
            
            # Fire prefetch for spotted entities (async, non-blocking)
            for entity_name in spotted:
                asyncio.create_task(prefetch_engine.on_message(session_id, entity_name))
            
            logger.info(f"Retrieved {len(final)} sessions for session {session_id}, entities: {spotted}")
            return {
                "sessions": final, 
                "from_cache": False, 
                "entities_spotted": spotted
            }
            
        except Exception as e:
            logger.error(f"Failed to get context for session {session_id}: {e}")
            return {"sessions": [], "from_cache": False, "entities_spotted": []}
    
    # ═══ MID-SESSION — ENTITY SPOTTING ═════════════════════════════════════
    
    async def on_user_message(self, session_id: str, message: str) -> None:
        """
        Call this on EVERY user message during a session.
        Non-blocking. Triggers prefetch in background.
        """
        try:
            await prefetch_engine.on_message(session_id, message)
        except Exception as e:
            logger.error(f"Error in on_user_message: {e}")
    
    # ═══ SESSION END — SAVE EVERYTHING ═════════════════════════════════════
    
    async def save_session(self, session_id: str, workflow_type: str,
                          messages: List[Dict], start_time: str,
                          notion_page_id: str = "") -> bool:
        """
        Called at the END of every session.
        Full write pipeline: extract → L4 → L3 → L2 → L1 cleanup
        
        Args:
            session_id: Unique session identifier
            workflow_type: Type of workflow (research, routine, etc.)
            messages: List of message dicts [{"role": "user"/"assistant", "content": str}]
            start_time: ISO datetime string when session started
            notion_page_id: Optional Notion page ID if created
            
        Returns:
            True on success, False on failure
        """
        try:
            end_time = datetime.utcnow().isoformat()
            
            # Step 1: Extract entities and summary
            logger.info(f"Extracting entities for session {session_id}...")
            extraction = await entity_extractor.extract(messages, workflow_type)
            entities = extraction["entities"]
            summary = extraction["summary"]
            primary_topic = extraction["primary_topic"]
            
            # Step 2: Build SessionMetadata
            # turn_id distinguishes this turn's L3/L4 record from other turns
            # in the same session, so per-turn writes accumulate instead of
            # overwriting each other.
            metadata = SessionMetadata(
                session_id=session_id,
                workflow_type=workflow_type,
                start_time=start_time,
                end_time=end_time,
                summary=summary,
                entities=entities,
                topics=[e.name for e in entities if e.entity_type == "TOPIC"] + ([primary_topic] if primary_topic else []),
                notion_page_id=notion_page_id,
                turn_id=str(uuid4())
            )
            
            # Step 3: L4 MongoDB — save full session
            saved_l4 = await l4_store.save_session(metadata, messages)
            
            # Step 4-6: Parallel writes to L3, L2 with error isolation
            # Use gather with return_exceptions to ensure all layers attempt write
            results = await asyncio.gather(
                self._save_to_l3(session_id, summary, metadata, entities),
                self._save_to_l2(session_id, entities, workflow_type, summary, metadata),
                return_exceptions=True
            )
            
            # Log any failures but don't crash
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    layer = ["L3", "L2"][idx]
                    logger.error(f"{layer} save failed for session {session_id}: {result}")
            
            # Step 7: L1 cleanup + refresh prefetch
            await l1_cache.flush_session_keys(session_id)
            await prefetch_engine.refresh_known_entities()
            
            # Invalidate entity caches that were updated this session
            for entity in entities:
                await l1_cache.invalidate_entity_context(entity.name)
            
            logger.info(f"Session {session_id} saved successfully. Entities: {[e.name for e in entities]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            return False
    
    async def _save_to_l3(self, session_id: str, summary: str, metadata: SessionMetadata, entities: List[Entity]) -> bool:
        """Save to Pinecone with error isolation.

        Vector ID is per-turn (session_id:turn_id) so each turn's summary
        gets its own embedding instead of overwriting prior turns' vectors.
        session_id is kept in metadata for retrieval grouping.
        """
        pinecone_meta = {
            "session_id": session_id,
            "workflow_type": metadata.workflow_type,
            "end_time": metadata.end_time,
            "topics": ",".join(metadata.topics),
            "entity_names": ",".join([e.name for e in entities])
        }
        vector_id = f"{session_id}:{metadata.turn_id}" if metadata.turn_id else session_id
        return await l3_vectors.upsert_session(vector_id, summary, pinecone_meta)
    
    async def _save_to_l2(self, session_id: str, entities: List[Entity], workflow_type: str, 
                         summary: str, metadata: SessionMetadata) -> bool:
        """Save to Neo4j with error isolation."""
        for entity in entities:
            await l2_graph.upsert_entity(entity.name, entity.entity_type, entity.description, entity.relation_to_user)
            await l4_store.save_entity(entity)
        
        await l2_graph.link_session_to_entities(
            session_id, entities, workflow_type, summary[:200]
        )
        
        # Update Karthik's current focus if a project was discussed
        projects = [e for e in entities if e.entity_type == "PROJECT"]
        if projects:
            await l2_graph.update_current_focus(projects[0].name)
        
        return True
    
    # ═══ PERMANENT MEMORY ════════════════════════════════════════════════
    
    async def remember(self, content: str, tags: List[str]) -> Dict:
        """Karthik says 'remember this' — store permanently."""
        try:
            doc = await l4_store.save_permanent_memory(content, tags)
            
            # Also store in vector search for semantic recall
            if doc.get("memory_id"):
                await l3_vectors.upsert_session(
                    f"permanent_{doc['memory_id']}", 
                    content,
                    {"type": "permanent", "tags": ",".join(tags)}
                )
            
            logger.info(f"Permanent memory saved: {doc.get('memory_id', 'UNKNOWN')}")
            return doc
            
        except Exception as e:
            logger.error(f"Failed to save permanent memory: {e}")
            return {}
    
    async def recall(self, query: str) -> List[Dict]:
        """Recall permanent memories matching a query."""
        try:
            # Vector search for permanent memories
            results = await l3_vectors.search_by_text(query, top_k=5)
            perm_ids = [
                r["session_id"].replace("permanent_", "")
                for r in results 
                if r["session_id"].startswith("permanent_")
            ]
            
            if perm_ids:
                memories = await l4_store.get_permanent_memories_by_tags([query])
                for m in memories:
                    await l4_store.increment_recalled_count(m["memory_id"])
                return memories
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to recall permanent memories: {e}")
            return []
    
    # ═══ CONTEXT FORMATTING ══════════════════════════════════════════════
    
    def format_context_for_prompt(self, context_result: Dict) -> str:
        """
        Formats retrieved context into a string for injection into system prompt.
        Returns empty string if no context.
        """
        sessions = context_result.get("sessions", [])
        if not sessions:
            return ""
        
        lines = ["--- RELEVANT PAST CONTEXT ---"]
        for s in sessions:
            workflow = s.get("workflow_type", "general")
            end_time = s.get("end_time", "")
            date = end_time[:10] if end_time else "unknown"  # Handle None end_time
            summary = s.get("summary", "")
            
            # Handle summary as list or string
            if isinstance(summary, list):
                summary = " ".join(str(item) for item in summary)
            elif not isinstance(summary, str):
                summary = str(summary)
                
            # Handle entities as None, list, or missing
            entity_list = s.get("entities", [])
            if entity_list is None:
                entity_list = []
            entities = ", ".join([e.get("name", "") for e in entity_list])
            
            lines.append(f"\n[{date} | {workflow}]")
            if entities:
                lines.append(f"Topics: {entities}")
            lines.append(summary)
        
        lines.append("--- END PAST CONTEXT ---")
        return "\n".join(lines)
    
    # ═══ HEALTH CHECK ════════════════════════════════════════════════════
    
    async def health_check(self) -> Dict:
        """Check health of all memory layers with a real live ping each --
        never assume a layer is healthy just because connect_all() didn't
        raise at startup (a dependency can die or become unreachable later)."""
        try:
            l1, l2, l3, l4 = await asyncio.gather(
                l1_cache.health_check(),
                l2_graph.health_check(),
                l3_vectors.health_check(),
                l4_store.health_check(),
            )
            return {
                "l1_redis": l1,
                "l2_neo4j": l2,
                "l3_pinecone": l3,
                "l4_mongodb": l4,
                "prefetch_queue_size": prefetch_engine.get_queue_size()
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "l1_redis": False,
                "l2_neo4j": False,
                "l3_pinecone": False,
                "l4_mongodb": False,
                "prefetch_queue_size": 0
            }

# Export singleton
memory_engine = MemoryEngine()