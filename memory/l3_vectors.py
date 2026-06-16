"""
ASTA Memory Layer - L3 Vector Store (Pinecone)
─────────────────────────────────────────────

This is the L3 semantic vector search layer using Pinecone.
Embeddings come from the unified memory embedding function
(memory.embeddings.embed → sentence-transformers all-MiniLM-L6-v2, 384 dims),
so upsert and query always agree on dimension EMBED_DIM.
"""

import asyncio
import logging
from typing import List, Dict, Optional
from pinecone import Pinecone, ServerlessSpec
from memory.embeddings import embed as _embed, EMBED_DIM
from backend.app.config import settings

logger = logging.getLogger(__name__)


def _parse_topics(value) -> List[str]:
    """Normalize Pinecone 'topics' metadata: writer stores a list, but legacy
    upserts may have stored a comma-separated string."""
    if isinstance(value, list):
        return value
    if value:
        return value.split(",")
    return []


class L3Vectors:
    """
    L3 semantic vector search layer using Pinecone.

    Uses the unified MiniLM embedding (EMBED_DIM dims) for both session-summary
    upserts and semantic queries.
    """
    
    def __init__(self):
        self.pc: Optional[Pinecone] = None
        self.index = None
        
    async def connect(self) -> None:
        """Initialize Pinecone client and Google AI."""
        try:
            # Initialize Pinecone
            self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)

            # Get or create index
            index_name = settings.PINECONE_INDEX_NAME

            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            index_names = [idx.name for idx in existing_indexes]

            if index_name not in index_names:
                # Create index sized to the unified embedding dimension
                self.pc.create_index(
                    name=index_name,
                    dimension=EMBED_DIM,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
                logger.info(f"Created new Pinecone index: {index_name} (dim={EMBED_DIM})")
            
            # Get index reference
            self.index = self.pc.Index(index_name)
            
            logger.info(f"L3 Pinecone connected, index: {index_name}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            raise
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Embed text with the unified MiniLM embedding (EMBED_DIM dims).
        Returns [] on bad input so callers can skip the upsert/query.
        """
        try:
            # Handle list inputs - join them
            if isinstance(text, list):
                logger.error("embed_text received list input - this should be handled at call site")
                text = " ".join(str(item) for item in text)
            elif not isinstance(text, str):
                text = str(text)

            if not text or not text.strip():
                logger.error("Empty or whitespace-only text provided for embedding")
                return []

            # Run the (CPU-bound) encode in a thread to avoid blocking the loop
            embedding = await asyncio.to_thread(_embed, text.strip())

            embedding_floats = [float(x) for x in embedding]
            if len(embedding_floats) != EMBED_DIM:
                logger.error(f"Unexpected embedding dimension: {len(embedding_floats)} (expected {EMBED_DIM})")
                return []

            return embedding_floats

        except Exception as e:
            logger.error(f"Failed to embed text: {e}")
            return []
    
    async def upsert_session(self, vector_id: str, summary: str, metadata: Dict) -> bool:
        """
        Embed session summary and upsert to Pinecone.

        Args:
            vector_id: Unique Pinecone vector ID for this record (e.g.
                "<session_id>:<turn_id>" for per-turn records, or a plain
                session_id for one-off records like permanent memories)
            summary: Session summary text to embed
            metadata: Dict with session metadata for filtering. If it
                contains "session_id", that value is stored in the vector's
                metadata for retrieval grouping; otherwise vector_id is used.

        Returns:
            True on success, False on failure
        """
        try:
            # Get embedding for summary
            embedding = await self.embed_text(summary)

            if not embedding:
                logger.error(f"Empty embedding for vector {vector_id}")
                return False

            # Prepare metadata for Pinecone (must be strings/numbers)
            pinecone_metadata = {
                "session_id": metadata.get("session_id", vector_id),
                "workflow_type": metadata.get("workflow_type", ""),
                "end_time": metadata.get("end_time", ""),
                "topics": metadata.get("topics", ""),  # comma-separated string
                "entity_names": metadata.get("entity_names", ""),  # comma-separated string
                "summary_snippet": summary[:200]  # First 200 chars
            }

            # Upsert vector
            self.index.upsert(
                vectors=[{
                    "id": vector_id,
                    "values": embedding,
                    "metadata": pinecone_metadata
                }]
            )

            logger.info(f"Vector {vector_id} upserted to L3")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert vector {vector_id}: {e}")
            return False
    
    async def search_by_text(self, query_text: str, top_k: int = 10, 
                            filter_session_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Semantic search by text query.
        
        Args:
            query_text: Text to search for
            top_k: Number of results to return
            filter_session_ids: Optional list of session IDs to filter by
            
        Returns:
            List of dicts with session_id, score, workflow_type, summary_snippet, topics
        """
        try:
            # Get embedding for query
            embedding = await self.embed_text(query_text)
            
            if not embedding:
                logger.error("Failed to embed query text")
                return []
            
            # Build filter
            filter_dict = None
            if filter_session_ids:
                filter_dict = {"session_id": {"$in": filter_session_ids}}
            
            # Query Pinecone
            def _query():
                return self.index.query(
                    vector=embedding,
                    top_k=top_k,
                    filter=filter_dict,
                    include_metadata=True
                )
            
            results = await asyncio.to_thread(_query)
            
            # Format results
            formatted_results = []
            for match in results.matches:
                formatted_results.append({
                    "session_id": match.metadata.get("session_id", ""),
                    "score": float(match.score),
                    "workflow_type": match.metadata.get("workflow_type", ""),
                    "summary_snippet": match.metadata.get("summary_snippet", ""),
                    "topics": _parse_topics(match.metadata.get("topics"))
                })

            logger.info(f"L3 search returned {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search by text: {e}")
            return []
    
    async def search_by_entity(self, entity_name: str, top_k: int = 5) -> List[Dict]:
        """
        Search for sessions related to a specific entity.
        
        Args:
            entity_name: Name of entity to search for
            top_k: Number of results to return
            
        Returns:
            Same format as search_by_text
        """
        try:
            # Embed entity name as query
            embedding = await self.embed_text(entity_name)
            
            if not embedding:
                return []
            
            # Filter by entity name in metadata
            filter_dict = {"entity_names": {"$eq": entity_name}}
            
            def _query():
                return self.index.query(
                    vector=embedding,
                    top_k=top_k,
                    filter=filter_dict,
                    include_metadata=True
                )
            
            results = await asyncio.to_thread(_query)
            
            # Format results (same as search_by_text)
            formatted_results = []
            for match in results.matches:
                formatted_results.append({
                    "session_id": match.metadata.get("session_id", ""),
                    "score": float(match.score),
                    "workflow_type": match.metadata.get("workflow_type", ""),
                    "summary_snippet": match.metadata.get("summary_snippet", ""),
                    "topics": _parse_topics(match.metadata.get("topics"))
                })

            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search by entity {entity_name}: {e}")
            return []
    
    async def delete_session_vector(self, session_id: str) -> None:
        """Delete vector by session ID."""
        try:
            def _delete():
                self.index.delete(ids=[session_id])
            
            await asyncio.to_thread(_delete)
            logger.info(f"Deleted vector for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete vector {session_id}: {e}")

# Export singleton
l3_vectors = L3Vectors()