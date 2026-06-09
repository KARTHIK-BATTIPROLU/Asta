"""
Embedding Service for ASTA Memory Layer
Uses sentence-transformers for 384-dim embeddings
Model is loaded once at module import time
"""
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("EmbeddingService")

# Load model ONCE at module import time
logger.info("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
_dim = 384
# Single source of truth for embedding dimension across the whole memory layer
# (Pinecone index dim, upsert, and query must all agree on this).
EMBED_DIM = _dim
logger.info("Sentence-transformers model loaded and ready")


def embed(text: str) -> list[float]:
    """
    Generate 384-dimensional embedding for text.
    Uses pre-loaded model (no lazy loading).
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        return [0.0] * _dim
    
    try:
        embedding = _model.encode(text).tolist()
        
        if len(embedding) != _dim:
            raise ValueError(f"Expected {_dim} dimensions, got {len(embedding)}")
        
        return embedding
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise


class EmbeddingService:
    """
    Legacy wrapper for backward compatibility.
    Uses the module-level embed() function.
    """
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        # Model is already loaded at module level
        self.model_name = model_name
        self.dim = _dim
        self.model = _model
        logger.info(f"EmbeddingService initialized (using pre-loaded model)")
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding using module-level function"""
        return embed(text)


# Global instance for backward compatibility
embedding_service = EmbeddingService()
