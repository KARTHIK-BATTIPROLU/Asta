import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
import math

from backend.app.services.memory.extractor import _generate_embedding
from backend.app.db.memory_handler import memory_handler
from backend.app.services.memory.graph_ltm import graph_ltm

logger = logging.getLogger("Recall")

def calculate_recency_score(ts: datetime) -> float:
    """Exponential decay, 30-day half-life."""
    if not ts:
        return 0.0
    
    # Ensure ts is timezone aware for comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
        
    delta_days = (datetime.now(timezone.utc) - ts).days
    # Half-life of 30 days: score = 0.5 ^ (days / 30)
    score = 0.5 ** (delta_days / 30.0)
    return max(0.0, min(1.0, score))

def calculate_behavioral_score(memory: Dict[str, Any]) -> float:
    """
    Max weight of linked priorities. 
    For now we use a heuristic based on confidence and pinned status.
    Real implementation would fetch the current priority weights and match entities.
    """
    score = memory.get("confidence", 0.5)
    
    if memory.get("pinned", False):
        score += 0.3
        
    return min(1.0, score)

async def recall(query: str, k: int = 6) -> List[Dict[str, Any]]:
    """
    Fetch candidate insights from Mongo (similarity pool) and Graphiti (relation pool),
    then score them based on: (0.5 * behavioral + 0.3 * recency + 0.2 * similarity)
    """
    # 1. Generate query embedding
    query_emb = await _generate_embedding(query)
    
    # 2. Fetch similarity pool
    cand = []
    if query_emb:
        cand = await memory_handler.get_relevant_insights(query_emb, top_k=24)
        
    # 3. Fetch relation pool from Graphiti
    graph_results = await graph_ltm.search(query, k=12)
    # graph_results would need to be normalized to match the cand format
    
    # Merge and dedupe
    seen_texts = set()
    merged = []
    
    for m in cand:
        text = m.get("text", "")
        if text not in seen_texts:
            seen_texts.add(text)
            merged.append(m)
            
    for g in graph_results:
        # Assuming g has a 'text' field or similar
        text = g.get("text", "")
        if text and text not in seen_texts:
            seen_texts.add(text)
            # Default similarity for graph hits if not provided
            g["similarity"] = g.get("similarity", 0.7) 
            merged.append(g)
            
    # 4. Score and Rank
    for m in merged:
        behavioral_score = calculate_behavioral_score(m)
        recency_score = calculate_recency_score(m.get("ts", datetime.now(timezone.utc)))
        similarity_score = m.get("similarity", 0.0)
        
        m["final_score"] = (0.5 * behavioral_score) + (0.3 * recency_score) + (0.2 * similarity_score)
        
    # Sort by final_score descending
    merged.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    
    top_matches = merged[:k]
    logger.info(f"[Recall] Retrieved top {len(top_matches)} memories for query.")
    return top_matches
