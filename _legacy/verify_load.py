import datetime
from datetime import timezone
import time
import os
import sys
import subprocess
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "asta_db"
COLLECTION_NAME = "reminders"

def verify_load():
    print("\n--- STEP 11: LOAD TEST (50 Reminders) ---")
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # 1. Insert 50 reminders
    count = 50
    print(f"📥 Inserting {count} reminders...")
    
    docs = []
    now = datetime.datetime.now(timezone.utc)
    for i in range(count):
        docs.append({
            "text": f"Load Test Reminder {i+1} 🚀",
            "remind_at": now,
            "status": "pending",
            "created_at": now
        })
    
    res = collection.insert_many(docs)
    ids = res.inserted_ids
    print(f"✅ Inserted {len(ids)} reminders.")
    
    # 2. Start Poller
    print("🚀 Starting Poller...")
    start_time = time.time()
    
    poller_process = subprocess.Popen(
        [sys.executable, "-m", "reminder_agent.poller"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    
    # 3. Wait/Monitor progress
    # Check every 5s until done or timeout (60s)
    timeout = 60
    while time.time() - start_time < timeout:
        processed = collection.count_documents({
            "_id": {"$in": ids},
            "status": {"$in": ["completed", "failed"]}
        })
        print(f"📊 Progress: {processed}/{count} ({int(processed/count*100)}%)")
        
        if processed == count:
            elapsed = time.time() - start_time
            print(f"✅ Load Test Passed! Processed {count} in {elapsed:.2f}s")
            poller_process.terminate()
            return True
            
        time.sleep(5)
        
    poller_process.terminate()
    print(f"❌ Load Test Failed! Timeout after {timeout}s. Processed {processed}/{count}.")
    
    outs, errs = poller_process.communicate()
    # Check output if partial failure
    return False

if __name__ == "__main__":
    if not verify_load():
        sys.exit(1)
    print("\n🎉 STEP 11 PASSED")