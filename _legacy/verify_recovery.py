import datetime
from datetime import timezone, timedelta
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

def verify_recovery():
    print("\n--- STEP 9: CRASH RECOVERY TEST ---")
    
    # 1. Insert Stale 'Sending' Reminder
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    stale_time = datetime.datetime.now(timezone.utc) - timedelta(minutes=10) # 10 mins old
    
    reminder_id = collection.insert_one({
        "text": "Crash Recovery Test ♻️",
        "remind_at": datetime.datetime.now(timezone.utc),
        "status": "sending", # Simulate stuck
        "claimed_at": stale_time,
        "created_at": datetime.datetime.now(timezone.utc)
    }).inserted_id
    
    print(f"✅ Inserted Stale Reminder: {reminder_id} (Status: sending, ClaimedAt: -10m)")
    
    # 2. Start Poller
    print("🚀 Starting Poller to recover...")
    poller_process = subprocess.Popen(
        [sys.executable, "-m", "reminder_agent.poller"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    
    # Wait for processing (Recovery happens at startup)
    print("⏳ Waiting 15s for recovery & processing...")
    time.sleep(15)
    poller_process.terminate()
    outs, errs = poller_process.communicate()
    
    # 3. Validation
    doc = collection.find_one({"_id": reminder_id})
    final_status = doc['status']
    print(f"✅ Final Status: {final_status}")
    
    if final_status == "completed":
        print("✅ Recovery Verified: Stale reminder was reset and processed.")
        return True
    else:
        print(f"❌ Recovery Failed! Status is {final_status}")
        print("🔍 Poller STDOUT:\n" + outs)
        print("🔍 Poller STDERR:\n" + errs)
        return False

if __name__ == "__main__":
    if not verify_recovery():
        sys.exit(1)
    print("\n🎉 STEP 9 PASSED")