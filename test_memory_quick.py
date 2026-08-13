"""Quick memory layer connectivity test - skips embedding model load"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

async def test_layers():
    print("=== Quick Memory Layer Connectivity Test ===\n")
    
    # Test L1 Redis
    print("Testing L1 (Redis)...")
    try:
        from memory.l1_cache import l1_cache
        await l1_cache.connect()
        healthy = await l1_cache.health_check()
        print(f"  L1 Redis: {'✓ HEALTHY' if healthy else '✗ FAILED'}\n")
    except Exception as e:
        print(f"  L1 Redis: ✗ FAILED - {e}\n")
    
    # Test L2 FalkorDB/Graphiti
    print("Testing L2 (FalkorDB/Graphiti)...")
    try:
        from backend.app.services.memory.graph_ltm import graph_ltm
        await graph_ltm.initialize()
        entities = await graph_ltm.get_all_entity_names()
        print(f"  L2 FalkorDB: ✓ CONNECTED (found {len(entities)} entities)\n")
    except Exception as e:
        print(f"  L2 FalkorDB: ✗ FAILED - {e}\n")
    

    
    # Test L4 MongoDB
    print("Testing L4 (MongoDB)...")
    try:
        from memory.l4_store import l4_store
        await l4_store.connect()
        healthy = await l4_store.health_check()
        print(f"  L4 MongoDB: {'✓ HEALTHY' if healthy else '✗ FAILED'}\n")
    except Exception as e:
        print(f"  L4 MongoDB: ✗ FAILED - {e}\n")
    
    # Test L3 Pinecone (without embedding - just connection)
    print("Testing L3 (Pinecone)...")
    try:
        from pinecone import Pinecone
        from backend.app.config import settings
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        indexes = pc.list_indexes()
        print(f"  L3 Pinecone: ✓ CONNECTED ({len(indexes)} indexes)\n")
    except Exception as e:
        print(f"  L3 Pinecone: ✗ FAILED - {e}\n")
    
    print("=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_layers())
