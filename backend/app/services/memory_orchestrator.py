import logging
import asyncio
import time
from datetime import datetime, timezone
from backend.app.db.database import db_manager
from backend.app.config import config
from backend.app.services.l2_manager import l2_manager
from backend.app.services.graph_service import l3_manager
from backend.app.core.registry import registry
from backend.app.core.circuit_breaker import circuit_l2_vector, circuit_l3_graph, status_registry

logger = logging.getLogger("Memory_Orchestrator")


class MemoryOrchestrator:
    """
    Unified memory pipeline:
      L1 overflow → L2 (MongoDB + Pinecone) → L3 (Neo4j graph)

    Retrieval priority:
      1. Pinecone vector search (fast, indexed)
      2. Neo4j graph traversal → MongoDB lookup (cross-tier)
      3. L2 brute-force MongoDB cosine similarity (last resort)
    """

    # ── L1 Overflow Handler ─────────────────────────────────────────────
    async def process_overflow(self, session_id: str, raw_segment: str):
        """
        Called when L1 cache evicts a turn.
        Pipelines: Summarize → Embed → MongoDB + Pinecone + Neo4j.
        Wrapped in asyncio.shield to ensure completion even if client disconnects.
        """
        async def _pipeline():
            try:
                logger.info(f"[Orchestrator] Processing L1 overflow for {session_id[:8]}...")

                # 1. L2: Summarize + Embed + Store to MongoDB (with circuit breaker)
                summary, l2_success = await circuit_l2_vector.call(
                    lambda: asyncio.to_thread(l2_manager.sync_process_and_store, session_id, raw_segment),
                    fallback="",
                    timeout_override=5.0  # Write operations get longer timeout
                )
                
                if not l2_success:
                    logger.warning(f"[Orchestrator] L2 processing bypassed due to circuit state or timeout")
                    await status_registry.update_health("l2_vector", False, {"error": "circuit_open_or_timeout"})
                else:
                    await status_registry.update_health("l2_vector", True)

                # 2. Pinecone: Upsert summary vector (only if L2 succeeded)
                if summary:
                    await self._upsert_to_pinecone(session_id, summary)

                    # 3. L3: Neo4j graph extraction (Queued properly avoiding 429 concurrent limit)
                    from backend.app.services.llm_queue import llm_queue
                    await llm_queue.enqueue(self._update_graph_with_circuit, session_id, summary)

            except Exception as e:
                logger.error(f"[Orchestrator] Overflow pipeline failed: {e}")

        # Run pipeline independently to prevent cancellation on socket close
        asyncio.create_task(_pipeline())

    # ── Pinecone Upsert ─────────────────────────────────────────────────
    async def _upsert_to_pinecone(self, session_id: str, summary: str):
        """
        Generates embedding and upserts to Pinecone.
        Isolated from MongoDB writes — failures here never block persistence.
        """
        try:
            vector_search = self._get_vector_service()
            if not vector_search:
                logger.warning("[RAG] Pinecone not registered — skipping upsert.")
                return

            embedding_service = self._get_embedding_service()
            if not embedding_service:
                logger.warning("[RAG] Embedding service not available — skipping upsert.")
                return

            vector = await asyncio.to_thread(embedding_service.embed, summary)
            if not vector:
                logger.warning("[RAG] Empty embedding generated — skipping upsert.")
                return

            logger.info(f"[RAG] Embedding generated, length={len(vector)}")

            vector_id = f"{session_id}::summary"
            metadata = {
                "session_id": session_id,
                "type": "summary",
                "summary": summary[:1000],  # Pinecone metadata limit
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await vector_search.upsert(id=vector_id, vector=vector, metadata=metadata)
            logger.info(f"[RAG] Pinecone upsert success: {vector_id}")

        except Exception as e:
            logger.error(f"[RAG] Pinecone upsert failed (non-blocking): {e}")

    async def _update_graph_with_circuit(self, session_id: str, summary: str):
        """L3 graph update with circuit breaker protection."""
        _, l3_success = await circuit_l3_graph.call(
            lambda: l3_manager.update_graph_knowledge(session_id, summary),
            fallback=None,
            timeout_override=5.0
        )
        
        if not l3_success:
            logger.warning(f"[Orchestrator] L3 graph update bypassed due to circuit state or timeout")
            await status_registry.update_health("l3_graph", False, {"error": "circuit_open_or_timeout"})
        else:
            await status_registry.update_health("l3_graph", True)

    # ── Speculative Prefetch Pipeline (L1.5 Layer) ──────────────────────
    async def speculative_prefetch(self, partial_query: str, session_id: str):
        """
        Runs asynchronously off the main thread when a non-final STT transcript hits.
        Identifies potential L3 property nodes, warms the L2 vector cache,
        and caches the result directly into L1.5 for a targeted 0ms resolution.
        """
        logger.info(f"[L1.5 Prefetch] Triggered for partial query: '{partial_query}'")
        try:
            from backend.app.services.action_dispatcher import dispatcher, IntentType
            intent = dispatcher.route_intent(partial_query)
            logger.info(f"[L1.5 Prefetch] Pre-classified Intent: {intent}")
            
            # Phase C Action Trigger
            if intent == IntentType.IDENTITY:
                # Trigger SkillsRetrieverTool defensively bypassing wait times for web searches.
                from backend.app.services.action_executor import action_executor
                from backend.app.models.action_model import ActionRequest
                
                req = ActionRequest(
                    session_id=session_id,
                    tool_name="SkillsRetriever",
                    parameters={"name": "KARTHIK"}
                )
                # Fire and forget execution to cache result into L1.5
                asyncio.create_task(action_executor.execute_action(req))
            elif intent == IntentType.ACTION:
                # If we recognize a task or action, we might set tool metadata 
                # (instead of just generic RAG) so the LLM invokes structured JSON.
                # Right now, we still fetch context, but we will tag it with the intent type.
                pass
            
            # Reusing cross_tier_retrieve logic asynchronously
            # This fetches the context, and stores it in the L1.5 speculative cache using the full query logic
            context_result = await self.cross_tier_retrieve(partial_query, top_k=2)
            
            if context_result.strip() and "I'm having trouble" not in context_result:
                # Wrap it with an intent hint if appropriate
                if intent != IntentType.CHITCHAT and intent != IntentType.IDENTITY:
                    context_result = f"[TRIGGERED_INTENT: {intent.value.upper()}]\n{context_result}"
                
                from backend.app.services.l1_cache import l1_manager
                await l1_manager.get_session(session_id).set_speculative_data(
                    key="prefetch_rag",
                    data=context_result,
                    ttl=10,
                    trigger_query=partial_query
                )
        except Exception as e:
            logger.error(f"[L1.5 Prefetch] Background failure: {e}", exc_info=True)

    # ── Retrieval Pipeline ──────────────────────────────────────────────
    async def cross_tier_retrieve(self, query: str, top_k: int = 3) -> str:
        """
        Multi-tier retrieval (Hydration Protocol) with circuit breaker protection:
          - Fetches Identity-First nodes (L3 - with circuit breaker).
          - Performs Vector Search (L2 - with circuit breaker).
          - Performs 2-hop Project Clustering (L3 - with circuit breaker).
        
        FALLBACK CHAIN:
          - If L3 fails → Widen L2 search
          - If L2 fails → Fall back to L1 context only
          
        Returns a formatted context string.
        """
        logger.info(f"[RAG] Starting cross_tier_retrieve for query: '{query}'")

        # Track overall retrieval status
        l2_available = not circuit_l2_vector.is_open
        l3_available = not circuit_l3_graph.is_open
        
        # 1. Identity-First (L3) - with strict 1000ms timeout
        identity_str = ""
        properties = []
        if l3_available:
            identity, identity_success = await circuit_l3_graph.call(
                lambda: l3_manager.get_user_identity("KARTHIK"),
                fallback={"name": "KARTHIK", "properties": [], "skills": [], "projects": []},
                timeout_override=5.0  # Increased for Neo4j warmups
            )
            if identity_success:
                properties = identity.get("properties", [])
                skills = identity.get("skills", [])
                projects = identity.get("projects", [])
                
                identity_str = (
                    f"Name: {identity.get('name', 'KARTHIK')}\n"
                    f"Known Properties: {', '.join(properties) if properties else 'None'}\n"
                    f"Skills: {', '.join(skills) if skills else 'None'}\n"
                    f"Projects: {', '.join(projects) if projects else 'None'}"
                )
                await status_registry.update_health("l3_graph", True)
            else:
                logger.warning("[RAG] L3 identity retrieval failed or timed out, using fallback")
                identity_str = "Name: KARTHIK\nKnown Properties: Unknown\nSkills: Unknown\nProjects: Unknown"
                await status_registry.update_health("l3_graph", False, {"error": "retrieval_timeout"})
        else:
            logger.warning("[RAG] L3 circuit OPEN, using identity fallback")
            identity_str = "Name: KARTHIK\nKnown Properties: Unknown (L3 unavailable)\nSkills: Unknown (L3 unavailable)\nProjects: Unknown (L3 unavailable)"

        # Find matching properties from the query
        matched_properties = [p for p in properties if p.lower() in query.lower()]
        filter_session_ids = None  # Allow global search fallback if no clusters match

        if l3_available and matched_properties:
            logger.info(f"[RAG] Query matches properties: {matched_properties}. Fetching clusters.")
            cluster_session_ids = set()
            for prop in matched_properties:
                start_l3 = time.time()
                sids, s_success = await circuit_l3_graph.call(
                    lambda: l3_manager.fetch_property_cluster(prop),
                    fallback=[],
                    timeout_override=5.0
                )
                logger.info(f"L3 Graph search completed in {time.time() - start_l3:.3f}s")
                if s_success and sids:
                    cluster_session_ids.update(sids)
            
            filter_session_ids = list(cluster_session_ids)
            logger.info(f"[RAG] Clusters resolved to {len(filter_session_ids)} specific sessions.")

        # 2. Semantic Search (L2/Vector) - with strict 1000ms timeout
        pinecone_results = []
        if l2_available:
            start_l2 = time.time()
            pinecone_results, l2_success = await circuit_l2_vector.call(
                lambda: self._query_pinecone(query, top_k, filter_session_ids=filter_session_ids),
                fallback=[],
                timeout_override=5.0  # Increased for Pinecone L2
            )
            logger.info(f"L2 Lookup took {time.time() - start_l2:.3f}s")
            if not l2_success:
                logger.warning("[RAG] L2 vector search failed or timed out")
                await status_registry.update_health("l2_vector", False, {"error": "retrieval_timeout"})
                # FALLBACK: Widen search if L3 is available
                if l3_available:
                    logger.info("[RAG] Attempting graph fallback for wider search")
                    pinecone_results = await self._fallback_to_graph(query, top_k)
        else:
            logger.warning("[RAG] L2 circuit OPEN, bypassing vector search")
            # FALLBACK: Try graph-based retrieval
            if l3_available:
                pinecone_results = await self._fallback_to_graph(query, top_k)

        # STRICT FALLBACK: If no results from filtered search, do global L2 search
        if not pinecone_results and filter_session_ids is not None:
            logger.info("[RAG] Strict fallback: Triggering global L2 search (L3 returned 0 results)")
            if l2_available:
                start_l2_global = time.time()
                pinecone_results, _ = await circuit_l2_vector.call(
                    lambda: self._query_pinecone(query, top_k, filter_session_ids=None),
                    fallback=[],
                    timeout_override=5.0
                )
                logger.info(f"L2 Lookup (global fallback) took {time.time() - start_l2_global:.3f}s")
            elif l3_available:
                # Last resort: graph fallback
                pinecone_results = await self._fallback_to_graph(query, top_k)

        session_ids = [r[0] for r in pinecone_results]
        summaries = [r[1] for r in pinecone_results]

        # 3. Target cluster visualization (Optional for context formatting)
        cluster_str = ""
        if matched_properties:
            cluster_str = "\n".join(f"- Active Topic: {p}" for p in matched_properties)

        if not cluster_str:
            cluster_str = "No specific active topics from the user's properties were mentioned in the current query."

        # 4. Build context
        history_str = "\n".join(f"- {s}" for s in summaries) if summaries else "No recent relevant sessions found."

        hydrated_context = (
            f"[USER PROFILE / IDENTITY]\n{identity_str}\n\n"
            f"[ACTIVE TOPICS MENTIONED IN LAST TURN]\n{cluster_str}\n\n"
            f"[ARCHIVAL MEMORY (L2/L3)]\n{history_str}"
        )
        mode = status_registry.get_memory_mode()
        logger.info(f"[RAG] Memory mode: {mode}")
        
        return hydrated_context

    async def _query_pinecone(self, query: str, top_k: int = 3, filter_session_ids: list[str] = None) -> list[tuple[str, str]]:
        """Queries Pinecone for semantically similar summaries. Returns list of (session_id, summary)."""
        try:
            vector_search = self._get_vector_service()
            if not vector_search:
                return []

            embedding_service = self._get_embedding_service()
            if not embedding_service:
                return []

            query_vector = await asyncio.to_thread(embedding_service.embed, query)
            if not query_vector:
                logger.warning("[RAG] Empty query embedding — skipping Pinecone query.")
                return []

            logger.info(f"[RAG] Querying Pinecone (top_k={top_k}, dim={len(query_vector)})...")
            
            query_kwargs = {"vector": query_vector, "top_k": top_k}
            if filter_session_ids is not None:
                if filter_session_ids:
                    query_kwargs["filter"] = {"session_id": {"$in": filter_session_ids}}
                else:
                    logger.info("[RAG] filter_session_ids is empty, ignoring graph domains and performing global vector search.")
            
            result = await vector_search.query(**query_kwargs)

            matches = getattr(result, "matches", []) or []
            logger.info(f"[RAG] Pinecone returned {len(matches)} matches.")

            results = []
            for match in matches:
                score = getattr(match, "score", 0)
                metadata = getattr(match, "metadata", {}) or {}
                summary = metadata.get("summary", "")
                session_id = metadata.get("session_id", "")
                if summary and score >= 0.3:
                    results.append((session_id, summary))
                    logger.info(f"[RAG] Match: score={score:.3f}, session={session_id[:8]}")

            return results
        except Exception as e:
            logger.error(f"[RAG] Pinecone query failed: {e}")
            return []

    async def _query_via_graph(self, query: str, top_k: int = 3) -> list[str]:
        """Uses Neo4j to find related session_ids, then fetches summaries from MongoDB."""
        try:
            session_ids = await l3_manager.query_related_sessions(query, limit=top_k)
            if not session_ids:
                return []

            if l2_manager.collection is None:
                return []

            docs = await asyncio.to_thread(
                lambda: list(
                    l2_manager.collection.find(
                        {"session_id": {"$in": session_ids}},
                        {"summary": 1},
                    )
                )
            )
            return [d["summary"] for d in docs if d.get("summary")]

        except Exception as e:
            logger.error(f"[RAG] Graph→MongoDB retrieval failed: {e}")
            return []

    async def _fallback_to_graph(self, query: str, top_k: int) -> list[tuple[str, str]]:
        """
        FALLBACK: When L2 (vector) is unavailable, try to retrieve via L3 graph.
        Uses Neo4j to find related sessions, then fetches from MongoDB.
        """
        try:
            start_l3_fallback = time.time()
            # Find related session IDs via graph
            session_ids, success = await circuit_l3_graph.call(
                lambda: l3_manager.query_related_sessions(query, limit=top_k),
                fallback=[],
                timeout_override=5.0
            )
            logger.info(f"L3 Graph search completed in {time.time() - start_l3_fallback:.3f}s")
            
            if not success or not session_ids:
                return []
            
            # Fetch summaries from MongoDB
            if l2_manager.collection is None:
                return []
            
            docs = await asyncio.to_thread(
                lambda: list(
                    l2_manager.collection.find(
                        {"session_id": {"$in": session_ids}},
                        {"summary": 1, "session_id": 1},
                    )
                )
            )
            
            results = []
            for doc in docs:
                sid = doc.get("session_id", "")
                summary = doc.get("summary", "")
                if sid and summary:
                    results.append((sid, summary))
            
            logger.info(f"[RAG] Graph fallback retrieved {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"[RAG] Graph fallback failed: {e}")
            return []

    # ── Service Helpers ─────────────────────────────────────────────────
    def _get_vector_service(self):
        """Safely retrieves the Pinecone vector service from registry."""
        try:
            return registry.get("vector")
        except KeyError:
            return None

    def _get_embedding_service(self):
        """Safely retrieves the embedding service from registry."""
        try:
            return registry.get("embedding")
        except KeyError:
            return None


orchestrator = MemoryOrchestrator()
