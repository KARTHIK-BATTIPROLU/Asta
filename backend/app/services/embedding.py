"""
ASTA embedding service — RETIRED duplicate.

This used to load its own MiniLM model in a ProcessPoolExecutor (a second copy
of the same model). It now delegates to the single unified embedding function
`memory.embeddings.embed` (sentence-transformers all-MiniLM-L6-v2, EMBED_DIM),
so there is exactly ONE embedding function and dimension across the app.

The EmbeddingService class + `embedding_service` singleton are kept so existing
registry consumers keep working.
"""
import asyncio
import logging

from memory.embeddings import embed as _embed, EMBED_DIM

logger = logging.getLogger(__name__)


class EmbeddingDimensionError(Exception):
    pass


class EmbeddingService:
    """Thin wrapper over the unified memory embedding function."""

    def __init__(self, model_name: str = None, max_workers: int = 2):
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"
        self.dim = EMBED_DIM
        logger.info("EmbeddingService initialized (delegating to memory.embeddings)")

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        return _embed(text)

    async def embed_async(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")
        return await asyncio.to_thread(_embed, text)

    def shutdown(self):
        pass  # no pool to drain anymore


embedding_service = EmbeddingService()
