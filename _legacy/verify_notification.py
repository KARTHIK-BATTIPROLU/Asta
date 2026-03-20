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

def verify_notification():
    print("\n--- STEP 5 & 6: POLLER & NOTIFICATION TEST ---")
    
    # 1. Insert Immediate Reminder
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    reminder_text = "Step 6 Verification Reminder 🔔"
    reminder_id = collection.insert_one({
        "text": reminder_text,
        "remind_at": datetime.datetime.now(timezone.utc),
        "status": "pending",
        "created_at": datetime.datetime.now(timezone.utc)
    }).inserted_id
    
    print(f"✅ Inserted Reminder: {reminder_id}")
    
    # 2. Start Poller
    print("🚀 Starting Poller...")
    poller_process = subprocess.Popen(
        [sys.executable, "-m", "reminder_agent.poller"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    
    # Wait for processing
    print("⏳ Waiting 15s for processing...")
    time.sleep(15)
    
    # 3. Check Status
    doc = collection.find_one({"_id": reminder_id})
    status = doc['status']
    print(f"✅ Final Status: {status}")
    
    # 4. Stop Poller
    poller_process.terminate()
    try:
        outs, errs = poller_process.communicate(timeout=5)
        print("📝 Poller STDOUT:")
        print(outs)
        print("📝 Poller STDERR:")
        print(errs)
    except:
        poller_process.kill()
        
    if status == "completed":
        print("✅ Notification Verified")
        return True
    else:
        print(f"❌ Notification Failed! Status is {status}")
        return False

if __name__ == "__main__":
    if not verify_notification():
        sys.exit(1)
    print("\n🎉 STEP 5 & 6 PASSED")