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

def verify_failure():
    print("\n--- STEP 8: FAILURE HANDLING TEST ---")
    
    # 1. Insert Failure Reminder
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    reminder_text = "Failure Test Reminder ❌"
    reminder_id = collection.insert_one({
        "text": reminder_text,
        "remind_at": datetime.datetime.now(timezone.utc),
        "status": "pending",
        "created_at": datetime.datetime.now(timezone.utc)
    }).inserted_id
    
    print(f"✅ Inserted Reminder: {reminder_id}")
    
    # 2. Start Poller with INVALID TOKEN
    print("🚀 Starting Poller with corrupted TELEGRAM_TOKEN...")
    
    env = os.environ.copy()
    env["TELEGRAM_TOKEN"] = "123456789:INVALID_TOKEN_FOR_TESTING" # Override
    
    poller_process = subprocess.Popen(
        [sys.executable, "-m", "reminder_agent.poller"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        env=env
    )
    
    # Wait for processing
    print("⏳ Waiting 15s for processing...")
    time.sleep(15)
    
    # 3. Validation
    # Drain output for debugging
    poller_process.terminate()
    outs, errs = poller_process.communicate()
    
    doc = collection.find_one({"_id": reminder_id})
    final_status = doc['status']
    print(f"✅ Final Status: {final_status}")
    
    if final_status == "failed":
        print("✅ Failure Handling Verified: Reminder marked as failed.")
        return True
    else:
        print(f"❌ Failure Handling Failed! Status is {final_status}")
        print("🔍 Poller STDOUT:\n" + outs)
        print("🔍 Poller STDERR:\n" + errs)
        return False

if __name__ == "__main__":
    if not verify_failure():
        sys.exit(1)
    print("\n🎉 STEP 8 PASSED")