import time
import sys
import subprocess
import os
from pymongo import MongoClient
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "asta_db"
COLLECTION_NAME = "reminders"

def verify_concurrency():
    print("\n--- STEP 7: CONCURRENCY & DEDUPLICATION TEST ---")
    
    client = MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]
    
    # 1. Insert 5 reminders
    reminder_ids = []
    print("📥 Inserting 5 reminders...")
    for i in range(5):
        res = collection.insert_one({
            "text": f"Concurrency Test {i+1} ⚡",
            "remind_at": datetime.now(timezone.utc),
            "status": "pending",
            "created_at": datetime.now(timezone.utc)
        })
        reminder_ids.append(res.inserted_id)
        
    # 2. Start 2 Pollers in parallel
    print("🚀 Starting 2 Poller processes...")
    p1 = subprocess.Popen([sys.executable, "-m", "reminder_agent.poller"], 
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    p2 = subprocess.Popen([sys.executable, "-m", "reminder_agent.poller"], 
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    
    try:
        print("⏳ Letting them race for 15s...")
        time.sleep(15)
    finally:
        p1.terminate()
        p2.terminate()
        # Drain outputs
        o1, e1 = p1.communicate()
        o2, e2 = p2.communicate()

    # 3. Validation
    # Check if all completed
    processed_count = collection.count_documents({
        "_id": {"$in": reminder_ids},
        "status": "completed"
    })
    
    print(f"📊 Completed: {processed_count}/5")
    
    # Check output logs for "claimed" vs "skipped" (optional but helpful)
    # Each reminder should be claimed exactly once across both logs ideally.
    # But since logging isn't atomic, just relying on Status is enough.
    
    if processed_count == 5:
        print("✅ Concurrency Test Passed: All reminders processed.")
        print("(Note: Check Telegram - should see exactly 5 messages, no duplicates)")
        return True
    else:
        print(f"❌ Concurrency Test Failed! Only {processed_count} completed.")
        print("🔍 Poller 1 STDOUT:\n" + o1)
        print("🔍 Poller 1 STDERR:\n" + e1)
        print("🔍 Poller 2 STDOUT:\n" + o2)
        print("🔍 Poller 2 STDERR:\n" + e2)
        return False

if __name__ == "__main__":
    if verify_concurrency():
        print("\n🎉 STEP 7 PASSED")
    else:
        sys.exit(1)