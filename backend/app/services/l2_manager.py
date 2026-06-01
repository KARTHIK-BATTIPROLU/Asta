"""
L2 Semantic RAG Memory Manager.

Handles extractive summarization (TextRank via summa)
and vector embedding generation. All MongoDB operations are async via db_manager.
"""

import logging
import asyncio
import numpy as np
from datetime import datetime, timezone
from summa import summarizer

from backend.app.db.database import db_manager

logger = logging.getLogger("L2_Semantic_RAG")


class L2MemoryManager:
    COLLECTION_NAME = "session_memory"

    def __init__(self):
        self.embedder = None
        logger.info("[L2_RAG] L2 Memory Manager initialized (using summa for summarization)")

    def _get_collection(self):
        """Get Motor async collection from unified db_manager."""
        if db_manager.db is None:
            return None
        return db_manager.db[self.COLLECTION_NAME]

    # ── CPU-bound ML stages (run in thread pool) ──────────────────────

    def _summarize_text(self, raw_text: str) -> str:
        """Extractive summarization using TextRank (summa)."""
        try:
            result = summarizer.summarize(raw_text, ratio=0.3)
            return result if result else raw_text[:300]
        except Exception as e:
            logger.error(f"[L2_RAG] Summarization failed: {e}")
            return raw_text[:300]

    def _generate_dense_vector(self, text: str) -> list[float]:
        """Maps text to 384-dimensional embedding via shared EmbeddingService."""
        try:
            from backend.app.core.registry import registry

            embedding_service = registry.get("embedding")
            if embedding_service:
                return embedding_service.embed(text)
        except Exception:
            pass
        if self.embedder:
            return self.embedder.encode(text).tolist()
        return []

    def _cpu_summarize(self, raw_segment: str) -> tuple[str, list[float]]:
        """
        CPU-bound pipeline: summarize → embed.
        Returns (summary_text, embedding_vector).
        Designed to run inside asyncio.to_thread().
        """
        summary = self._summarize_text(raw_segment)
        vector = self._generate_dense_vector(summary)
        return summary, vector

    # ── Async entry points ────────────────────────────────────────────

    async def async_process_and_store(self, session_id: str, raw_segment: str) -> str:
        """
        Full L2 pipeline: summarize + embed (in thread) → async upsert to MongoDB.
        Returns the generated summary for downstream L3 processing.
        """
        logger.info("[L2_RAG] Executing TextRank summarization.")

        # CPU-bound ML inference runs in thread pool
        summary, vector = await asyncio.to_thread(self._cpu_summarize, raw_segment)

        doc = {
            "session_id": session_id,
            "raw_segment_ref": [raw_segment],
            "summary": summary,
            "embedding": vector,
            "created_at": datetime.now(timezone.utc),
        }

        collection = self._get_collection()
        if collection is not None:
            try:
                await collection.update_one(
                    {"session_id": session_id},
                    {"$set": doc},
                    upsert=True,
                )
                logger.info(f"[L2_RAG] Memory embedded to DB for {session_id}")
            except Exception as e:
                logger.error(f"[L2_RAG] MongoDB upsert failed for {session_id}: {e}")
        else:
            logger.warning("[L2_RAG] MongoDB unavailable — summary not persisted.")

        return summary

    async def auto_summarize_and_store(self, session_id: str, raw_segment: str):
        """Async entry point for L1 overflow processing."""
        if not raw_segment or len(raw_segment.strip()) < 10:
            return
        await self.async_process_and_store(session_id, raw_segment)

    async def query_memory(self, query_text: str, top_k: int = 3) -> list[str]:
        """Async semantic search over session_memory collection."""
        # Embedding generation is CPU-bound
        query_vector = await asyncio.to_thread(self._generate_dense_vector, query_text)
        if not query_vector:
            return []

        collection = self._get_collection()
        if collection is None:
            return []

        try:
            cursor = collection.find({}, {"summary": 1, "embedding": 1})
            memories = await cursor.to_list(length=500)

            scored_memories = []
            q_arr = np.array(query_vector)
            q_norm = np.linalg.norm(q_arr)

            if q_norm == 0:
                return []

            for mem in memories:
                emb = mem.get("embedding")
                if not emb or len(emb) == 0:
                    continue

                emb_arr = np.array(emb)
                mem_norm = np.linalg.norm(emb_arr)

                if mem_norm == 0:
                    continue

                sim = float(np.dot(q_arr, emb_arr) / (q_norm * mem_norm))
                scored_memories.append((sim, mem.get("summary", "")))

            filtered = [m for m in scored_memories if m[0] >= 0.1]
            filtered.sort(key=lambda x: x[0], reverse=True)

            return [m[1] for m in filtered[:top_k]]

        except Exception as e:
            logger.error(f"[L2_RAG] RAG query failed: {e}")
            return []


l2_manager = L2MemoryManager()
