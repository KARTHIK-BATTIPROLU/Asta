"""
Memory Handler — async insights collection access.

Stores and retrieves individual session insights with their embeddings via the unified db_manager.
All operations are async. No PyMongo sync calls.
"""

import logging
import math
from datetime import datetime, timezone
from typing import List, Dict, Any

try:
    import numpy as np
except ImportError:
    np = None

from backend.app.db.database import db_manager

logger = logging.getLogger(__name__)


class MemoryHandler:
    """Async memory handler for insights collection."""

    COLLECTION_NAME = "insights"

    def _get_collection(self):
        """Get the insights collection from unified db_manager."""
        if db_manager.db is None:
            return None
        return db_manager.db[self.COLLECTION_NAME]

    async def store_insight(self, session_id: str, kind: str, text: str, entities: List[str], confidence: float, embedding: List[float], pinned: bool = False) -> bool:
        """Store a single insight + embedding vector to MongoDB."""
        collection = self._get_collection()
        if collection is None:
            logger.warning("[MEMORY] MongoDB collection not available to store insight.")
            return False

        now = datetime.now(timezone.utc)
        doc = {
            "session_id": session_id,
            "ts": now,
            "kind": kind,
            "text": text,
            "entities": entities,
            "confidence": confidence,
            "embedding": embedding,
            "pinned": pinned
        }

        try:
            await collection.insert_one(doc)
            logger.debug(f"[MEMORY] Insight stored for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"[MEMORY] Failed to store insight: {e}")
            return False

    async def get_relevant_insights(self, query_embedding: List[float], top_k: int = 24) -> List[Dict[str, Any]]:
        """Retrieves top_k similar insights from MongoDB via cosine similarity."""
        collection = self._get_collection()
        if collection is None:
            logger.warning("[MEMORY] MongoDB collection not available for retrieval.")
            return []

        try:
            # For Phase 3, we fetch all insights and score them in-memory if Atlas Vector Search is not configured.
            # In a production setup, this would be an aggregate with $vectorSearch.
            cursor = collection.find({}, {"text": 1, "embedding": 1, "kind": 1, "entities": 1, "pinned": 1, "ts": 1})
            memories = await cursor.to_list(length=1000)

            if not memories:
                return []

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

                mem["similarity"] = sim
                scored_memories.append(mem)

            # Pre-filter by baseline similarity before full ranking logic
            threshold = 0.3
            filtered_results = [m for m in scored_memories if m["similarity"] > threshold]
            filtered_results.sort(key=lambda x: x["similarity"], reverse=True)
            
            top_matches = filtered_results[:top_k]
            return top_matches

        except Exception as e:
            logger.error(f"[MEMORY] Retrieval failed: {e}")
            return []


memory_handler = MemoryHandler()
