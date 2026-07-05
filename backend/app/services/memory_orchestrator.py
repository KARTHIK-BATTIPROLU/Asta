"""
Memory Orchestrator — Speculative prefetch + retrieval pipeline for ASTA.

Retrieval: delegates to memory_engine.get_context_for_session (single memory brain)
"""

import logging
from backend.app.core.task_registry import TaskRegistry

logger = logging.getLogger("Memory_Orchestrator")


class MemoryOrchestrator:
    """
    Unified memory pipeline:
      Prefetch: speculative L1.5 cache warming for in-flight STT transcripts
      Read:     memory_engine.get_context_for_session (L2 Neo4j → L3 Pinecone → L4 Mongo)
    """

    def __init__(self):
        self._active_tasks: set = set()

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
            logger.error(f"[L1.5] Prefetch cache failed: {e}", exc_info=True)

    # ── Retrieval Pipeline (unified) ─────────────────────────────────────
    async def cross_tier_retrieve(self, query: str, top_k: int = 8) -> str:
        """
        Delegates to the unified memory_engine (Neo4j cluster search →
        Pinecone vector search → Mongo) — the single memory brain. Returns
        formatted context for prompt injection.
        """
        try:
            from memory import memory_engine
            ctx = await memory_engine.get_context_for_session(
                session_id="retrieval", user_input=query, workflow_type="general"
            )
            return memory_engine.format_context_for_prompt(ctx)
        except Exception as e:
            logger.warning(f"[RAG] memory_engine retrieval failed: {e}")
            return ""


orchestrator = MemoryOrchestrator()
