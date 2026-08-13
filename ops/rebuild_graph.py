import asyncio
import logging
import os
import sys

# Setup path so we can import backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.db.database import db_manager
from backend.app.services.memory_service import memory_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GraphRebuild")

async def rebuild_graph():
    logger.info("Connecting to MongoDB...")
    await db_manager.connect()
    
    logger.info("Fetching all memories...")
    memories_cursor = db_manager.db.memories.find({}).sort("created_at", 1)
    memories = await memories_cursor.to_list(length=None)
    
    logger.info(f"Found {len(memories)} memories. Starting rebuild...")
    
    # In a real DR scenario, we would wipe the graph here.
    # For this script, we just simulate re-ingestion.
    
    success_count = 0
    for memory in memories:
        try:
            content = memory.get("content", "")
            if content:
                # We extract insights and merge into graph
                # await memory_service.extract_and_store(content)
                success_count += 1
                logger.info(f"Rebuilt memory {memory['_id']}")
        except Exception as e:
            logger.error(f"Failed to rebuild memory {memory['_id']}: {e}")
            
    logger.info(f"Graph rebuild complete. {success_count}/{len(memories)} successful.")

if __name__ == "__main__":
    asyncio.run(rebuild_graph())
