"""Direct layer connectivity test - no memory module imports"""
import asyncio
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient
from pinecone import Pinecone
from neo4j import AsyncGraphDatabase
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from backend.app.config import settings

async def test_connections():
    print("=== Direct Layer Connectivity Test ===\n")
    results = {}
    
    # Test L1 Redis
    print("1. Testing L1 (Redis)...")
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        results["L1_Redis"] = "✓ CONNECTED"
        await client.aclose()
    except Exception as e:
        results["L1_Redis"] = f"✗ FAILED: {e}"
    print(f"   {results['L1_Redis']}\n")
    
    # Test L2 Neo4j
    print("2. Testing L2 (Neo4j)...")
    try:
        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
        )
        async with driver.session() as session:
            result = await session.run("RETURN 1 as test")
            await result.consume()
        results["L2_Neo4j"] = "✓ CONNECTED"
        await driver.close()
    except Exception as e:
        results["L2_Neo4j"] = f"✗ FAILED: {e}"
    print(f"   {results['L2_Neo4j']}\n")
    
    # Test L2 FalkorDB (if configured)
    print("3. Testing L2 Graphiti (FalkorDB)...")
    try:
        falkor_host = getattr(settings, "FALKORDB_HOST", None)
        falkor_port = getattr(settings, "FALKORDB_PORT", None)
        
        if falkor_host and falkor_port:
            # FalkorDB uses Redis protocol
            import redis as sync_redis
            r = sync_redis.Redis(host=falkor_host, port=int(falkor_port), decode_responses=True)
            r.ping()
            results["L2_FalkorDB"] = "✓ CONNECTED"
            r.close()
        else:
            results["L2_FalkorDB"] = "⚠ NOT CONFIGURED"
    except Exception as e:
        results["L2_FalkorDB"] = f"✗ FAILED: {e}"
    print(f"   {results['L2_FalkorDB']}\n")
    
    # Test L3 Pinecone
    print("4. Testing L3 (Pinecone)...")
    try:
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        indexes = pc.list_indexes()
        index_names = [idx.name for idx in indexes]
        results["L3_Pinecone"] = f"✓ CONNECTED ({len(index_names)} indexes: {', '.join(index_names)})"
    except Exception as e:
        results["L3_Pinecone"] = f"✗ FAILED: {e}"
    print(f"   {results['L3_Pinecone']}\n")
    
    # Test L4 MongoDB
    print("5. Testing L4 (MongoDB)...")
    try:
        client = AsyncIOMotorClient(settings.MONGO_URI)
        await client.admin.command('ping')
        db = client[settings.DB_NAME]
        collections = await db.list_collection_names()
        results["L4_MongoDB"] = f"✓ CONNECTED ({len(collections)} collections)"
        client.close()
    except Exception as e:
        results["L4_MongoDB"] = f"✗ FAILED: {e}"
    print(f"   {results['L4_MongoDB']}\n")
    
    # Summary
    print("="*50)
    print("SUMMARY:")
    print("="*50)
    for layer, status in results.items():
        print(f"{layer:15} : {status}")
    print("="*50)
    
    # Count working layers
    working = sum(1 for v in results.values() if v.startswith("✓"))
    total = len([k for k in results.keys() if not results[k].startswith("⚠")])
    print(f"\n{working}/{total} layers operational")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_connections())
