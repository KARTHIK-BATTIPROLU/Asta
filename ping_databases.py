import asyncio
import time
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase

# Import your configurations
from backend.app.config import config

async def measure_mongo_latency():
    print("--- MongoDB Latency Test ---")
    
    # 1. Instantiate the Mongo Client
    client = AsyncIOMotorClient(
        config.MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000
    )
    db = client[config.MONGO_DB_NAME if hasattr(config, 'MONGO_DB_NAME') else 'asta']
    
    # Measure Ping Latency
    start_time = time.perf_counter()
    try:
        await client.admin.command("ping")
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"[MongoDB] Ping latency: {elapsed_ms:.2f} ms")
    except Exception as e:
        print(f"[MongoDB] Ping failed: {e}")

    # Measure Read Latency (fetching a single document)
    start_time = time.perf_counter()
    try:
        await db["sessions"].find_one()
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"[MongoDB] Read latency: {elapsed_ms:.2f} ms")
    except Exception as e:
        print(f"[MongoDB] Read failed: {e}")
    finally:
        client.close()

async def measure_neo4j_latency():
    print("\n--- Neo4j Latency Test ---")
    
    if not all([config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD]):
        print("Neo4j credentials missing in config.")
        return

    driver = AsyncGraphDatabase.driver(
        config.NEO4J_URI, 
        auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD), 
        connection_timeout=5.0
    )
    
    # Measure Ping Latency
    start_time = time.perf_counter()
    try:
        await driver.verify_connectivity()
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"[Neo4j] Ping latency: {elapsed_ms:.2f} ms")
    except Exception as e:
        print(f"[Neo4j] Ping failed: {e}")

    # Measure Read Latency (Simple Cypher query)
    start_time = time.perf_counter()
    try:
        async with driver.session() as session:
            await session.run("MATCH (n) RETURN n LIMIT 1")
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"[Neo4j] Read latency: {elapsed_ms:.2f} ms")
    except Exception as e:
        print(f"[Neo4j] Read failed: {e}")
    finally:
        await driver.close()

async def run_latency_checks():
    await measure_mongo_latency()
    await measure_neo4j_latency()

if __name__ == "__main__":
    asyncio.run(run_latency_checks())
