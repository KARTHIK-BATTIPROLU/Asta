import asyncio
import logging
from backend.app.config import config
from backend.app.core.registry import registry
from backend.app.services.embedding import EmbeddingService
from backend.app.services.memory_orchestrator import orchestrator
from backend.app.services.graph_service import l3_manager
from backend.app.db.database import db_manager

logging.basicConfig(level=logging.INFO)

async def test():
    await db_manager.connect()
    embedding_service = EmbeddingService()
    registry.register("embedding", embedding_service)
    
    if config.PINECONE_API_KEY:
        from pinecone import Pinecone
        pc = Pinecone(api_key=config.PINECONE_API_KEY)
        pinecone_index = pc.Index(config.PINECONE_INDEX_NAME)

        class PineconeVectorSearch:
            def __init__(self, index):
                self._index = index
            async def upsert(self, id, vector, metadata):
                pass
            async def query(self, vector, top_k, **kwargs):
                return await asyncio.to_thread(
                    self._index.query, vector=vector, top_k=top_k, include_metadata=True, **kwargs
                )
        registry.register("vector", PineconeVectorSearch(pinecone_index))
    
    await l3_manager.initialize_base_graph()

    res = await orchestrator.cross_tier_retrieve("what are my skills")
    print("MATCHES:", res)
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test())
