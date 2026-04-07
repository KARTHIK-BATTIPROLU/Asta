"""
ASTA Memory Pipeline End-to-End Validation Script
Tests: L1 Buffer → L2 MongoDB + Pinecone → L3 Neo4j Graph

Usage:
    python -m simulate_memory
"""
import asyncio
import time
import uuid
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Memory_Validation")

DUMMY_TURNS = [
    {
        "user": "Hey ASTA, I've been organizing the application architecture.",
        "assistant": "That's great Karthik! Which application architecture are you structuring?"
    },
    {
        "user": "Well, primarily Maestro. I'm building out the new Inventory tracking modules. We need to implement Flutter so the mobile app scales natively across environments without rewriting logic.",
        "assistant": "Got it. So replacing native code with Flutter inside Maestro's UI stack. I will track that update."
    },
    {
        "user": "I also mapped out the Federated ML execution loops inside Scam Shield. Keeping data localized on the mobile node is going to prevent server overloads.",
        "assistant": "Excellent. Federated ML will definitely lower inference costs for Scam Shield. Any other project updates?"
    },
    {
        "user": (
            "Yeah, GrowHub needs better backend APIs for the AI Entrepreneurship modules. "
            + ("Here is a massive token block to force L1 cache evictions. " * 200)
        ),
        "assistant": "Understood. The 2000 token limit will be forcefully breached now."
    },
]


async def validation_script():
    # ── Phase 0: Boot Services ──────────────────────────────────────
    logger.info("=" * 60)
    logger.info("ASTA Memory Pipeline Validation — Starting")
    logger.info("=" * 60)

    from backend.app.db.database import db_manager
    from backend.app.config import config
    from backend.app.core.registry import registry
    from backend.app.services.embedding import EmbeddingService
    from backend.app.services.l1_cache import l1_manager
    from backend.app.services.l2_manager import l2_manager
    from backend.app.services.memory_orchestrator import orchestrator
    from backend.app.services.graph_service import l3_manager
    from backend.app.db.mongo import MongoDB

    await db_manager.connect()
    MongoDB.connect()

    # Register embedding service
    embedding_service = EmbeddingService()
    registry.register("embedding", embedding_service)
    logger.info("[BOOT] Embedding service registered.")

    # Register Pinecone (if configured)
    pinecone_available = False
    if config.PINECONE_API_KEY:
        try:
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
            pinecone_available = True

            stats = pinecone_index.describe_index_stats()
            vec_count = getattr(stats, "total_vector_count", 0)
            dimension = getattr(stats, "dimension", 0)
            logger.info(f"[BOOT] Pinecone connected: {vec_count} vectors, dim={dimension}")
        except Exception as e:
            logger.warning(f"[BOOT] Pinecone unavailable: {e}")
    else:
        logger.warning("[BOOT] PINECONE_API_KEY not set — Pinecone tests will be skipped.")

    # Initialize base graph
    await l3_manager.initialize_base_graph()

    session_id = str(uuid.uuid4())
    logger.info(f"[TEST] Session ID: {session_id}")

    # ── Phase 1: Ingest Turns (L1 → L2 overflow) ───────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 1: Ingesting turns through L1 buffer")
    logger.info("=" * 60)

    cache = l1_manager.get_session(session_id)

    for i, turn in enumerate(DUMMY_TURNS):
        t0 = time.perf_counter()
        await cache.append_turn(turn["user"], turn["assistant"])
        latency = (time.perf_counter() - t0) * 1000
        logger.info(f"[Turn {i}] L1 append: {latency:.1f}ms")

    # Wait for fire-and-forget tasks (L2 MongoDB + Pinecone + L3 Neo4j)
    logger.info("[TEST] Waiting 12s for async pipeline tasks to complete...")
    await asyncio.sleep(12)

    # ── Phase 2: Verify MongoDB ─────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 2: Verifying MongoDB (session_memory)")
    logger.info("=" * 60)

    if l2_manager.collection is not None:
        docs = list(l2_manager.collection.find({"session_id": session_id}))
        logger.info(f"[MONGO] Found {len(docs)} document(s) for session {session_id[:8]}")
        for doc in docs:
            summary = doc.get("summary", "N/A")
            emb_len = len(doc.get("embedding", []))
            logger.info(f"  Summary: {summary[:100]}...")
            logger.info(f"  Embedding length: {emb_len}")
    else:
        logger.warning("[MONGO] session_memory collection not available.")

    # ── Phase 3: Verify Pinecone ────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 3: Verifying Pinecone RAG retrieval")
    logger.info("=" * 60)

    if pinecone_available:
        test_query = "What did we discuss about ASTA?"
        logger.info(f"[RAG] Test query: '{test_query}'")

        results = await orchestrator._query_pinecone(test_query, top_k=3)
        if results:
            logger.info(f"[RAG] ✅ Pinecone returned {len(results)} match(es):")
            for idx, r in enumerate(results):
                logger.info(f"  [{idx}] {r[:120]}...")
        else:
            logger.warning("[RAG] ⚠️ Pinecone returned 0 matches. Vectors may not have been upserted yet.")

        # Also test the full cross_tier_retrieve
        logger.info(f"[RAG] Testing cross_tier_retrieve('{test_query}')...")
        cross_results = await orchestrator.cross_tier_retrieve(test_query)
        if cross_results:
            logger.info(f"[RAG] ✅ Cross-tier returned {len(cross_results)} match(es):")
            for idx, r in enumerate(cross_results):
                logger.info(f"  [{idx}] {r[:120]}...")
        else:
            logger.warning("[RAG] ⚠️ Cross-tier returned 0 matches.")
    else:
        logger.info("[RAG] Skipping Pinecone tests (not configured).")

    # ── Phase 4: Verify Neo4j Graph ─────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 4: Verifying Neo4j Graph")
    logger.info("=" * 60)

    driver = db_manager.neo4j_driver
    if driver:
        # Test 1: Base graph structure
        try:
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (u:Person {name: 'Karthik'})-[:HAS_CATEGORY]->(c:Category) "
                    "RETURN c.name AS category"
                )
                records = await result.data()
                categories = [r["category"] for r in records]
                logger.info(f"[GRAPH] ✅ Base graph categories: {categories}")
        except Exception as e:
            logger.error(f"[GRAPH] Base graph test failed: {e}")

        # Test 2: Session nodes and relationships
        try:
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (u:Person {name: 'Karthik'})-[:HAS_SESSION]->(s:Session)-[:RELATES_TO]->(entity) "
                    "RETURN s.session_id AS session_id, labels(entity) AS entity_type, entity.name AS entity_name"
                )
                records = await result.data()
                if records:
                    logger.info(f"[GRAPH] ✅ Found {len(records)} session→entity relationships:")
                    for r in records:
                        sid = r["session_id"][:8] if r.get("session_id") else "N/A"
                        logger.info(f"  Session {sid}.. → {r['entity_type']}: {r['entity_name']}")
                else:
                    logger.warning("[GRAPH] ⚠️ No session relationships found yet.")
        except Exception as e:
            logger.error(f"[GRAPH] Session relationship test failed: {e}")

        # Test 3: Full graph dump
        try:
            if hasattr(l3_manager, "get_full_graph"):
                graph_data = await l3_manager.get_full_graph()
                logger.info(f"[GRAPH] Full graph has {len(graph_data)} relationships:")
                for row in graph_data[:20]:
                    logger.info(
                        f"  ({row.get('from_name')}) -[{row.get('relationship')}]-> ({row.get('to_name')})"
                    )
            else:
                logger.info("[GRAPH] Skipping get_full_graph (method removed in Solar System refactor).")
        except Exception as e:
            logger.error(f"[GRAPH] Full graph dump failed: {e}")
    else:
        logger.warning("[GRAPH] Neo4j driver not available — skipping graph tests.")

    # ── Summary ─────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 60)

    await db_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(validation_script())
