import logging
import asyncio
from sentence_transformers import SentenceTransformer
from backend.app.config import config

logger = logging.getLogger(__name__)

class EmbeddingDimensionError(Exception):
    """Raised when generated embedding has invalid dimensions."""
    pass

class EmbeddingService:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or getattr(config, "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        self.model = None
        self.dim = getattr(config, "PINECONE_EMBEDDING_DIM", 384)
        self._load_model()

    def _load_model(self):
        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.model = None

    def embed(self, text: str) -> list[float]:
        """
        Synchronously generates an embedding for the given text.
        Returns an empty list if the model is not loaded.
        """
        if not self.model or not text.strip():
            return []
        try:
            # Returns a numpy array, convert to list of floats for MongoDB
            embedding = self.model.encode(text).tolist()
            if len(embedding) != self.dim:
                raise EmbeddingDimensionError(f"Expected dim {self.dim}, got {len(embedding)}")
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise  # Bubble up the error instead of returning empty list

    async def embed_async(self, text: str) -> list[float]:
        """
        Asynchronously generates an embedding for the given text.
        Safe to call from async event loops.
        """
        if not text.strip():
            logger.warning("Empty text provided for async embedding")
            raise ValueError("Cannot embed empty text")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)
