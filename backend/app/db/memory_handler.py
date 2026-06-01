"""
Memory Handler — async session_memory collection access.

Stores and retrieves session memory embeddings via the unified db_manager.
All operations are async. No PyMongo sync calls.
"""

import logging
import math
from datetime import datetime, timezone
from typing import List

try:
    import numpy as np
except ImportError:
    np = None

from backend.app.db.database import db_manager

logger = logging.getLogger(__name__)


class MemoryHandler:
    """Async memory handler for session_memory collection."""

    COLLECTION_NAME = "session_memory"

    def _get_collection(self):
        """Get the session_memory collection from unified db_manager."""
        if db_manager.db is None:
            return None
        return db_manager.db[self.COLLECTION_NAME]

    async def store_memory(self, session_id: str, summary: str, embedding: List[float]) -> bool:
        """Store a session summary + embedding vector to MongoDB."""
        collection = self._get_collection()
        if collection is None:
            logger.warning("[MEMORY] MongoDB collection not available to store memory.")
            return False

        now = datetime.now(timezone.utc)
        doc = {
            "session_id": session_id,
            "summary": summary,
            "embedding": embedding,
            "timestamp": now,
        }

        try:
            await collection.update_one(
                {"session_id": session_id},
                {"$set": doc},
                upsert=True,
            )
            logger.info(f"[MEMORY] Summary stored and embedding generated for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"[MEMORY] Failed to store memory: {e}")
            return False

    async def get_relevant_memories(self, query_embedding: List[float], top_k: int = 3) -> List[str]:
        """Retrieves top_k similar summaries from session_memory via cosine similarity."""
        collection = self._get_collection()
        if collection is None:
            logger.warning("[MEMORY] MongoDB collection not available for retrieval.")
            return []

        try:
            cursor = collection.find({}, {"summary": 1, "embedding": 1})
            memories = await cursor.to_list(length=500)

            if not memories:
                logger.info("[MEMORY] No previous memories found.")
                return []

            logger.info(f"[MEMORY] RETRIEVAL TRIGGERED. Searching {len(memories)} memories.")

            scored_memories = []
            for mem in memories:
                emb = mem.get("embedding")
                if not emb or not isinstance(emb, list) or len(emb) == 0:
                    continue

                # Cosine similarity calculation
                if np is not None:
                    vec1 = np.array(query_embedding)
                    vec2 = np.array(emb)
                    norm1 = np.linalg.norm(vec1)
                    norm2 = np.linalg.norm(vec2)
                    if norm1 == 0 or norm2 == 0:
                        continue
                    sim = float(np.dot(vec1, vec2) / (norm1 * norm2))
                else:
                    dot = sum(a * b for a, b in zip(query_embedding, emb))
                    norm1 = math.sqrt(sum(a * a for a in query_embedding))
                    norm2 = math.sqrt(sum(b * b for b in emb))
                    if norm1 == 0 or norm2 == 0:
                        continue
                    sim = dot / (norm1 * norm2)

                scored_memories.append((sim, mem.get("summary", "")))

            logger.info(f"[MEMORY] Retrieved {len(scored_memories)} results")

            threshold = 0.45
            filtered_results = [m for m in scored_memories if m[0] > threshold]
            filtered_results.sort(key=lambda x: x[0], reverse=True)
            top_matches = [m[1] for m in filtered_results[:top_k] if m[1]]

            if top_matches:
                logger.info(f"[MEMORY] TOP MATCHES FOUND: {len(top_matches)} matches")
            return top_matches

        except Exception as e:
            logger.error(f"[MEMORY] Retrieval failed: {e}")
            return []


memory_handler = MemoryHandler()
