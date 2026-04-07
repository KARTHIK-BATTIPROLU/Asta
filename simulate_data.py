import asyncio
import random
import uuid
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load the .env configuration explicitly
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("CRITICAL: MONGO_URI not found in the current .env file!")

DB_NAME = "asta"
COLLECTION_NAME = "sessions"

# Data Generation Dictionaries
INTENTS = ["reminder", "knowledge_query", "task_update", "calendar_sync", "telegram_alert"]
LOCATIONS = ["Gandipet", "Hyderabad", "CBIT Campus", "Remote Office"]
DEVICES = ["Mobile - iOS", "Mobile - Android", "Laptop - MacBook Air", "Desktop - polyglot"]

DUMMY_TRANSCRIPTS = [
    "Hey Asta, check if my Notion project timeline for Maestro has been updated.",
    "Asta, send a Telegram alert to the dev group that the API is failing.",
    "Can you remind me tomorrow morning at 8am to review the Flutter UI branch?",
    "Add a Google Calendar event for Friday afternoon: Scam Shield core pitch presentation.",
    "What's the exact dimension size for a sentence-transformers float array?",
    "Asta, log a task update: GrowHub integration is officially pushed to staging.",
    "Hey, any new notifications from the college group chat on Telegram?",
    "Remind me in 30 minutes to take my medications.",
    "Are there any blocking bugs reported on the Maestro inventory logic?",
    "Asta, what's a fast way to execute PageRank maths in Python on localized CPUs?",
    "Can you summarize the Neo4j association nodes for my current active projects?",
    "Save a note: Scam Shield needs a cleaner UI loading structure by Monday.",
    "Clear my afternoon Google Calendar layout, I need focus time for coding.",
    "Hey Asta, push a status update to Notion: Redis architecture is successfully scaling.",
    "Did I miss any critical deadlines for the CBIT presentation?",
    "Send a quick Telegram message to Sir telling him I'll be 10 minutes late.",
    "Log progress on Maestro: Barcode scanner integration is 50 percent finalized.",
    "Asta, what is the best strategy for deploying Nginx WebSockets without dropping?",
    "Hey, check my upcoming Notion tasks for the weekend.",
    "Remind me to drink water and stand up in exactly one hour.",
    "Can you quickly parse the Flutter docs and tell me why this widget tree is clipping?",
    "Asta, start a focus timer for 45 minutes targeting GrowHub logic."
]

def generate_timestamp(days_back: int = 7) -> str:
    """Generates a random ISO timestamp cleanly constrained over the past week."""
    random_days = random.uniform(0, days_back)
    past_time = datetime.utcnow() - timedelta(days=random_days)
    return past_time.isoformat() + "Z"

def generate_dummy_session() -> dict:
    """Builds a robust, production-mirroring dummy interaction log."""
    transcript = random.choice(DUMMY_TRANSCRIPTS)
    
    # Simple heuristic to assign intent properly
    if "remind" in transcript.lower():
        intent = "reminder"
    elif "telegram" in transcript.lower() or "alert" in transcript.lower() or "message" in transcript.lower():
        intent = "telegram_alert"
    elif "calendar" in transcript.lower():
        intent = "calendar_sync"
    elif "update" in transcript.lower() or "log" in transcript.lower() or "save a note" in transcript.lower():
        intent = "task_update"
    else:
        intent = "knowledge_query"

    return {
        "session_id": str(uuid.uuid4()),
        "user_id": "user_karthik_01",
        "timestamp": generate_timestamp(),
        "transcript": transcript,
        "intent": intent,
        "metadata": {
            "device": random.choice(DEVICES),
            "latency_ms": random.randint(45, 140),
            "location": random.choice(LOCATIONS),
            "audio_length_seconds": round(random.uniform(1.5, 6.2), 2)
        }
    }

async def run_simulation():
    print("\n[ASTA Simulation] Booting MongoDB connection...")
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        # Ensure we are strictly pinging
        await client.admin.command('ping')
        print("[ASTA Simulation] Connection Verified. Generating Datasets...")
        
        # Build payload
        dummy_payloads = [generate_dummy_session() for _ in range(25)]
        
        # Bulk Insert
        result = await collection.insert_many(dummy_payloads)
        
        print(f"✔️ Successfully inserted {len(result.inserted_ids)} 'Real-World' dummy records!")
        print(f"Sample Document:\n{dummy_payloads[0]}\n")
        
    except Exception as e:
        print(f"[ASTA Simulation] Error executing pipeline: {e}")
    finally:
        if 'client' in locals():
            client.close()
            print("[ASTA Simulation] MongoDB socket cleanly collapsed.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
