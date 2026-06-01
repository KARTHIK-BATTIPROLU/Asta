import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
from sentence_transformers import SentenceTransformer
from backend.app.config import config

logger = logging.getLogger(__name__)

# Global storage inside the worker processes
_worker_model = None
_worker_dim = None

def _init_worker(model_name: str, dim: int):
    """
    Called once per worker to independently load the model context.
    """
    global _worker_model, _worker_dim
    try:
        # Note: Suppress noisy sentence-transformers loading logs here if needed
        _worker_model = SentenceTransformer(model_name)
        _worker_dim = dim
    except Exception as e:
        logger.error(f"[Worker] Failed to load embedding model: {e}")
        _worker_model = None

def _embed_worker(text: str) -> list[float]:
    """
    Runs isolated in child process.
    """
    global _worker_model, _worker_dim
    if not _worker_model:
        raise RuntimeError("Worker model not initialized")
    
    if not text.strip():
        raise ValueError("Cannot embed empty text")
    
    try:
        embedding = _worker_model.encode(text).tolist()
        if len(embedding) != _worker_dim:
            raise ValueError(f"Expected dim {_worker_dim}, got {len(embedding)}")
        return embedding
    except Exception as e:
        # Log with more context
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[Worker] Error generating embedding for text '{text[:50]}...': {e}")
        raise

class EmbeddingDimensionError(Exception):
    pass

class EmbeddingService:
    def __init__(self, model_name: str = None, max_workers: int = 2):
        self.model_name = model_name or getattr(config, "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        self.dim = getattr(config, "PINECONE_EMBEDDING_DIM", 384)
        
        # Init Process Pool Executor
        self.executor = ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_worker,
            initargs=(self.model_name, self.dim)
        )
        logger.info(f"ProcessPoolExecutor initialized with {max_workers} workers for embedding.")

    def embed(self, text: str) -> list[float]:
        """
        Synchronously blocks until embedding is calculated by pool worker.
        """
        if not text.strip():
            return []
        try:
            future = self.executor.submit(_embed_worker, text)
            result = future.result(timeout=15)
            logger.debug(f"Generated embedding for text: {text[:50]}... (dim={len(result)})")
            return result
        except Exception as e:
            logger.error(f"Error generating embedding for text '{text[:50]}...': {e}")
            raise  # Re-raise instead of swallowing

    async def embed_async(self, text: str) -> list[float]:
        """
        Asynchronously awaits embedding offloaded to the ProcessPoolExecutor.
        """
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, _embed_worker, text)

    def shutdown(self):
        """Cleanly drains the process pool"""
        logger.info("Shutting down Embedding Process Pool...")
        self.executor.shutdown(wait=True)

    def __del__(self):
        try:
            self.shutdown()
        except:
            pass

embedding_service = EmbeddingService()
