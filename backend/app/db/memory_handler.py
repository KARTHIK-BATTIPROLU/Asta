import logging
from datetime import datetime, timezone
from typing import List
import math

try:
    import numpy as np
except ImportError:
    np = None

from backend.app.db.mongo import MongoDB

logger = logging.getLogger(__name__)

class MemoryHandler:
    @property
    def collection(self):
        # We use a distinct collection for session_memory
        return MongoDB.db["session_memory"] if MongoDB.db is not None else None

    def store_memory(self, session_id: str, summary: str, embedding: List[float]) -> bool:
        if self.collection is None:
            logger.warning("[MEMORY] MongoDB collection not available to store memory.")
            return False
            
        now = datetime.now(timezone.utc)
        doc = {
            "session_id": session_id,
            "summary": summary,
            "embedding": embedding,
            "timestamp": now
        }
        
        try:
            # Upsert by session_id to avoid duplicates
            self.collection.update_one(
                {"session_id": session_id},
                {"$set": doc},
                upsert=True
            )
            logger.info(f"[MEMORY] SUMMARY STORED and EMBEDDING GENERATED for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"[MEMORY] Failed to store memory: {e}")
            return False

    def get_relevant_memories(self, query_embedding: List[float], top_k: int = 3) -> List[str]:
        """
        Retrieves top_k similar summaries from session_memory.
        """
        if self.collection is None:
            logger.warning("[MEMORY] MongoDB collection not available for retrieval.")
            return []
            
        try:
            cursor = self.collection.find({}, {"summary": 1, "embedding": 1})
            memories = list(cursor)
            
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
                    sim = np.dot(vec1, vec2) / (norm1 * norm2)
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
