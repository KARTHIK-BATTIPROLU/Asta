import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

async def clear_db():
    print("[Clear DB] Connecting to Mongo...")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client["asta"]
    
    # Target "sessions" specifically requested
    res1 = await db["sessions"].delete_many({})
    print(f"Deleted {res1.deleted_count} documents from 'sessions'.")
    
    # Target potential L2 vector overlap
    res2 = await db["session_memory"].delete_many({})
    print(f"Deleted {res2.deleted_count} documents from 'session_memory'.")
    
    client.close()
    print("[Clear DB] Done.")

if __name__ == "__main__":
    asyncio.run(clear_db())
