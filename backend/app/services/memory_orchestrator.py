"""
Memory Orchestrator — Unified write + retrieval pipeline for ASTA.

Write path: L1 overflow → CPU summarize → MemorySaga (atomic 3-phase)
Retrieval: Parallel Neo4j identity + Pinecone semantic → Late Fusion (RRF)
"""

import logging
import asyncio
import time
from datetime import datetime, timezone
from backend.app.db.database import db_manager
from backend.app.config import config
from backend.app.services.l2_manager import l2_manager
from memory.graph_service import graph_service as l3_manager
from backend.app.core.registry import registry
from backend.app.core.circuit_breaker import circuit_l2_vector, circuit_l3_graph, status_registry
from backend.app.core.task_registry import TaskRegistry

logger = logging.getLogger("Memory_Orchestrator")


class MemoryOrchestrator:
    """
    Unified memory pipeline:
      Write: L1 overflow → MemorySaga (Outbox → Mongo + Pinecone + Neo4j)
      Read:  Parallel Neo4j + Pinecone → RRF Late Fusion → Structured XML

    Retrieval target: <200ms via parallel fetching.
    Write target: Zero data loss via Outbox Pattern + retry worker.
    """

    def __init__(self):
        self._active_tasks: set = set()

    # ── L1 Overflow Handler ─────────────────────────────────────────────
    async def process_overflow(self, session_id: str, raw_segment: str):
        """
        Called when L1 cache evicts a turn.
        Pipeline: Summarize → Embed (CPU-bound) → MemorySaga (atomic 3-phase write).
        The Saga guarantees MongoDB, Pinecone, and Neo4j stay in sync.
        """
        async def _pipeline():
            try:
                logger.info(f"[Orchestrator] Processing L1 overflow for {session_id[:8]}...")

                # 1. CPU-bound: Summarize + Embed (via L2 manager thread pool)
                summary, embedding = await asyncio.to_thread(
                    l2_manager._cpu_summarize, raw_segment
                )

                if not summary:
                    logger.warning(f"[Orchestrator] Empty summary for {session_id[:8]} — skipping")
                    return

                # 2. Atomic write via MemorySaga (Outbox Pattern)
                from memory.memory_saga import MemorySaga
                saga = MemorySaga(
                    session_id=session_id,
                    summary=summary,
                    embedding=embedding,
                    raw_segment=raw_segment,
                    source="overflow",
                )
                all_ok = await saga.execute()

                if all_ok:
                    await status_registry.update_health("l2_vector", True)
                else:
                    logger.warning(f"[Orchestrator] Partial saga for {session_id[:8]} — retry worker will handle")

            except Exception as e:
                logger.error(f"[Orchestrator] Overflow pipeline failed for {session_id[:8]}: {e}")

        # Run pipeline independently — tracked and supervised by TaskRegistry
        TaskRegistry.track(
            _pipeline(),
            name=f"memory_overflow_pipeline:{session_id[:8]}",
            session_id=session_id,
        )

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
            
            if intent == IntentType.IDENTITY:
                from backend.app.services.action_executor import action_executor
                from backend.app.models.action_model import ActionRequest
                
                req = ActionRequest(
                    session_id=session_id,
                    tool_name="SkillsRetriever",
                    parameters={"name": "KARTHIK"}
                )
                TaskRegistry.track(
                    action_executor.execute_action(req),
                    name=f"skills_retriever_prefetch:{session_id[:8]}",
                    session_id=session_id,
                )
            elif intent == IntentType.ACTION:
                pass
            
            context_result = await self.cross_tier_retrieve(partial_query, top_k=5)
            
            if context_result.strip() and "No relevant" not in context_result:
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

    # ── Retrieval Pipeline (unified) ─────────────────────────────────────
    async def cross_tier_retrieve(self, query: str, top_k: int = 8) -> str:
        """
        RETIRED duplicate → now delegates to the unified memory_engine
        (Neo4j cluster search → Pinecone vector search → Mongo), so there is a
        single memory brain. Returns formatted context for prompt injection.
        Falls back to the legacy parallel pipeline only if the engine errors.
        """
        try:
            from memory import memory_engine
            ctx = await memory_engine.get_context_for_session(
                session_id="retrieval", user_input=query, workflow_type="general"
            )
            return memory_engine.format_context_for_prompt(ctx)
        except Exception as e:
            logger.warning(f"[RAG] Unified engine retrieval failed ({e}); using legacy pipeline")
            return await self._legacy_cross_tier_retrieve(query, top_k)

    async def _legacy_cross_tier_retrieve(self, query: str, top_k: int = 8) -> str:
        """Legacy parallel Neo4j+Pinecone+RRF pipeline (fallback only)."""
        start_time = time.time()
        logger.info(f"[RAG] Starting parallel cross_tier_retrieve for: '{query[:50]}'")

        PARALLEL_TIMEOUT = 1.5  # seconds — hard limit for voice pipeline

        # ── Phase 1: Fire all fetches in parallel ────────────────────────
        async def _fetch_identity():
            """Fetch user identity + properties from Neo4j."""
            result, success = await circuit_l3_graph.call(
                lambda: l3_manager.get_user_identity("KARTHIK"),
                fallback={"name": "KARTHIK", "properties": [], "skills": [], "projects": []},
                timeout_override=PARALLEL_TIMEOUT,
            )
            return result, success

        async def _fetch_graph_context():
            """Get relevant session_ids from graph clusters."""
            try:
                result = await asyncio.wait_for(
                    l3_manager.get_graph_context(query, session_id="retrieval"),
                    timeout=PARALLEL_TIMEOUT
                )
                return result.get("session_ids", []), True
            except Exception as e:
                logger.warning(f"[RAG] Graph context fetch failed: {e}")
                return [], False

        async def _fetch_semantic(filter_session_ids=None):
            """Semantic search via Pinecone with optional graph-based filtering."""
            results, success = await circuit_l2_vector.call(
                lambda: self._query_pinecone(query, top_k=top_k, filter_session_ids=filter_session_ids),
                fallback=[],
                timeout_override=PARALLEL_TIMEOUT,
            )
            return results, success

        # Run identity and graph context in parallel first
        try:
            (identity_result, id_success), (filter_session_ids, graph_success) = await asyncio.gather(
                _fetch_identity(),
                _fetch_graph_context(),
            )
        except Exception as e:
            logger.error(f"[RAG] Parallel fetch (phase 1) failed: {e}")
            identity_result = {"name": "KARTHIK", "properties": [], "skills": [], "projects": []}
            id_success = False
            filter_session_ids = []
            graph_success = False

        # Now fetch from Pinecone with optional filtering
        if filter_session_ids and graph_success:
            logger.info(f"[RAG] Using graph-filtered search with {len(filter_session_ids)} sessions")
            pinecone_results, pc_success = await _fetch_semantic(filter_session_ids=filter_session_ids)
        else:
            logger.info(f"[RAG] Using global semantic search (no graph filter)")
            pinecone_results, pc_success = await _fetch_semantic(filter_session_ids=None)

        # ── Phase 2: Extract identity fields ─────────────────────────────
        if id_success:
            properties = identity_result.get("properties", [])
            skills = identity_result.get("skills", [])
            projects = identity_result.get("projects", [])
            await status_registry.update_health("l3_graph", True)
        else:
            properties, skills, projects = [], [], []
            await status_registry.update_health("l3_graph", False, {"error": "retrieval_failed"})

        if pc_success:
            await status_registry.update_health("l2_vector", True)
        else:
            await status_registry.update_health("l2_vector", False, {"error": "retrieval_failed"})

        # ── Phase 3: Late Fusion via Reciprocal Rank Fusion ──────────────
        RRF_K = 60  # Standard RRF constant
        fused_results = {}  # session_id -> {summary, score}

        for rank, (session_id, summary) in enumerate(pinecone_results):
            rrf_score = 1.0 / (rank + RRF_K)
            key = session_id or f"anon_{rank}"
            if key not in fused_results or rrf_score > fused_results[key]["score"]:
                fused_results[key] = {"summary": summary, "score": rrf_score}

        # Sort by RRF score and take top results
        sorted_results = sorted(fused_results.values(), key=lambda x: x["score"], reverse=True)
        top_summaries = [r["summary"] for r in sorted_results[:top_k]]

        # ── Phase 4: Format structured context ───────────────────────────
        elapsed = time.time() - start_time
        mode = status_registry.get_memory_mode()
        logger.info(
            f"[RAG] Retrieval completed in {elapsed:.3f}s "
            f"(mode={mode}, results={len(top_summaries)})"
        )

        return self._format_structured_context(
            identity_result if id_success else None,
            properties, skills, projects,
            top_summaries,
        )

    # ── Structured Context Formatter (Component 9) ───────────────────────
    def _format_structured_context(
        self,
        identity: dict | None,
        properties: list,
        skills: list,
        projects: list,
        episodic_summaries: list,
    ) -> str:
        """
        Format retrieval results as structured XML context for LLM injection.
        Clear XML boundaries prevent hallucination from flat context blobs.
        """
        name = identity.get("name", "KARTHIK") if identity else "KARTHIK"
        props_str = ", ".join(properties) if properties else "None available"
        skills_str = ", ".join(skills) if skills else "None available"
        projects_str = ", ".join(projects) if projects else "None available"

        if episodic_summaries:
            episodes = "\n".join(f"    <episode>{s}</episode>" for s in episodic_summaries)
        else:
            episodes = "    <episode>No relevant past sessions found.</episode>"

        context = (
            "<memory_context>\n"
            "  <core_identity>\n"
            f"    <name>{name}</name>\n"
            f"    <active_projects>{projects_str}</active_projects>\n"
            f"    <known_skills>{skills_str}</known_skills>\n"
            f"    <known_properties>{props_str}</known_properties>\n"
            "  </core_identity>\n"
            "  <episodic_recall>\n"
            f"{episodes}\n"
            "  </episodic_recall>\n"
            "  <tool_history>\n"
            "    <note>No recent tool executions.</note>\n"
            "  </tool_history>\n"
            "</memory_context>"
        )

        return context

    # ── Pinecone Query ──────────────────────────────────────────────────
    async def _query_pinecone(self, query: str, top_k: int = 8, filter_session_ids: list[str] = None) -> list[tuple[str, str]]:
        """Queries Pinecone for semantically similar summaries."""
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

            query_kwargs = {"vector": query_vector, "top_k": top_k}
            if filter_session_ids:
                query_kwargs["filter"] = {"session_id": {"$in": filter_session_ids}}
            
            result = await vector_search.query(**query_kwargs)
            matches = getattr(result, "matches", []) or []

            results = []
            for match in matches:
                score = getattr(match, "score", 0)
                metadata = getattr(match, "metadata", {}) or {}
                summary = metadata.get("summary", "")
                session_id = metadata.get("session_id", "")
                if summary and score >= 0.25:
                    results.append((session_id, summary))

            return results
        except Exception as e:
            logger.error(f"[RAG] Pinecone query failed: {e}")
            return []

    async def _fallback_to_graph(self, query: str, top_k: int) -> list[tuple[str, str]]:
        """FALLBACK: When L2 unavailable, retrieve via L3 graph → MongoDB."""
        try:
            session_ids, success = await circuit_l3_graph.call(
                lambda: l3_manager.query_related_sessions(query, limit=top_k),
                fallback=[],
                timeout_override=1.5,
            )
            
            if not success or not session_ids:
                return []
            
            collection = db_manager.get_collection("session_memory")
            cursor = collection.find(
                {"session_id": {"$in": session_ids}},
                {"summary": 1, "session_id": 1},
            )
            docs = await cursor.to_list(length=top_k)
            
            return [
                (doc.get("session_id", ""), doc.get("summary", ""))
                for doc in docs
                if doc.get("session_id") and doc.get("summary")
            ]
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
