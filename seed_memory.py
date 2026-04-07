import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Seed_Memory")

async def seed_karthik_knowledge():
    logger.info("Starting Knowledge Ingestion Protocol...")

    # Boot Services
    from backend.app.db.database import db_manager
    from backend.app.config import config
    from backend.app.core.registry import registry
    from backend.app.services.embedding import EmbeddingService
    from backend.app.services.memory_orchestrator import MemoryOrchestrator
    from backend.app.db.mongo import MongoDB

    await db_manager.connect()
    MongoDB.connect()

    # Register embedding service
    embedding_service = EmbeddingService()
    registry.register("embedding", embedding_service)

    # Register Pinecone
    if config.PINECONE_API_KEY:
        from pinecone import Pinecone
        pc = Pinecone(api_key=config.PINECONE_API_KEY)
        pinecone_index = pc.Index(config.PINECONE_INDEX_NAME)

        class PineconeVectorSearch:
            def __init__(self, index):
                self._index = index

            async def upsert(self, id: str, vector: list, metadata: dict):
                await asyncio.to_thread(
                    self._index.upsert, vectors=[(id, vector, metadata)]
                )

            async def query(self, vector: list, top_k: int = 5, **kwargs):
                return await asyncio.to_thread(
                    self._index.query,
                    vector=vector, top_k=top_k, include_metadata=True, **kwargs,
                )

        registry.register("vector", PineconeVectorSearch(pinecone_index))
        logger.info("Pinecone service registered.")
    else:
        logger.warning("PINECONE_API_KEY not set. Vector ingestion will be skipped.")

    mo = MemoryOrchestrator()

    # 1. Inject Graph Identity (Neo4j)
    logger.info("Step 1: Populating Neo4j Identity...")
    driver = db_manager.neo4j_driver
    if driver:
        query = """
        // Core Identity Node
        MERGE (u:Identity {name: "KARTHIK"})
        SET u.role = "2nd Year AI & Data Science Student at CBIT",
            u.location = "Gandipet, Hyderabad"
            
        // Map Skills
        MERGE (s1:Skill {name: "Python"})
        MERGE (u)-[:HAS_SKILL]->(s1)

        MERGE (s2:Skill {name: "Flutter"})
        MERGE (u)-[:HAS_SKILL]->(s2)

        MERGE (s3:Skill {name: "Java"})
        MERGE (u)-[:HAS_SKILL]->(s3)

        // Map Projects
        MERGE (p1:Project {name: "ASTA"})
        MERGE (u)-[:DEVELOPING]->(p1)

        MERGE (p2:Project {name: "GrowHub"})
        MERGE (u)-[:DEVELOPING]->(p2)

        MERGE (p3:Project {name: "Lazy Learner"})
        MERGE (u)-[:COMPLETED]->(p3)

        MERGE (p4:Project {name: "Aarohan"})
        MERGE (u)-[:HACKATHON]->(p4)
        """
        try:
            async with driver.session() as session:
                await session.run(query)
            logger.info("Successfully ingested Identity, Skills, and Projects into Neo4j graph.")
        except Exception as e:
            logger.error(f"Failed to populate Neo4j: {e}")
    else:
        logger.warning("Neo4j driver is not available.")

    # 2. Inject Simulated Sessions (Pinecone + MongoDB)
    fake_sessions = [
        {
            "id": "seed_growhub_001",
            "query": "Asta, how should I structure the multi-agent workflow for GrowHub?",
            "response": "For GrowHub, you should use a 'Manager-Worker' pattern. The Manager agent handles the user intent, while worker agents handle specific tasks like website building and social media marketing."
        },
        {
            "id": "seed_metaverse_002",
            "query": "I'm worried about metaverse interoperability. What are the standards?",
            "response": "Karthik, you should look into the Metaverse Standards Forum. Focus on USD (Universal Scene Description) and glTF for 3D asset interoperability across Unity environments."
        },
        {
            "id": "seed_dsa_003",
            "query": "Should I stick with Python for DSA or switch to Java?",
            "response": "Since you're targeting high-performance roles, Java's strict typing and vast library support for collections make it a standard for DSA, though Python is faster for prototyping AI models."
        }
    ]

    logger.info("Step 2: Embedding synthetic sessions into L1 overflow (Mongo + Pinecone)...")
    for session in fake_sessions:
        raw_segment = f"User: {session['query']}\nAssistant: {session['response']}"
        logger.info(f"Injecting Session: {session['id']}...")
        
        # Await the execution of process_overflow
        await mo.process_overflow(
            session_id=session["id"],
            raw_segment=raw_segment
        )

    # Allow fire-and-forget tasks spawned by process_overflow to finish processing/embedding
    logger.info("Waiting 10s to ensure internal pipelines persist to L2 and L3...")
    await asyncio.sleep(10)

    logger.info("✅ Memory Seeding Complete. ASTA is now context-aware.")
    
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(seed_karthik_knowledge())
