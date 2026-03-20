import datetime
from datetime import timezone
import time
import os
import sys
import subprocess
from pymongo import MongoClient
import dateparser
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "asta_db"
COLLECTION_NAME = "reminders"

def verify_timezone_wait():
    print("\n--- STEP 10: TIMEZONE WAIT TEST ---")
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # 0. Clean DB
    collection.delete_many({})
    
    # 1. Parse "in 60 seconds"
    # Using the agent's logic (which uses dateparser)
    # Ideally reuse asta.py logic but we simulate insertion directly for now
    # to test the Poller's respecting of remind_at
    
    now_utc = datetime.datetime.now(timezone.utc)
    remind_at = now_utc + datetime.timedelta(seconds=45) # 45s from now
    
    print(f"🕒 Now (UTC): {now_utc}")
    print(f"⏰ Remind At (UTC): {remind_at}")
    
    res = collection.insert_one({
        "text": "Timezone Wait Test ⏳",
        "remind_at": remind_at,
        "status": "pending",
        "created_at": now_utc
    })
    r_id = res.inserted_id
    print(f"✅ Inserted Reminder: {r_id}")
    
    # 2. Start Poller
    print("🚀 Starting Poller...")
    # Redirect output to file
    with open("poller_timezone.log", "w", encoding="utf-8") as log_file:
        poller_process = subprocess.Popen(
            [sys.executable, "-m", "reminder_agent.poller"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8'
        )
        
        try:
            # 3. Check IMMEDIATELY (should be pending)
            print("🛑 Checking immediate status (should be pending)...")
            time.sleep(5)
            doc = collection.find_one({"_id": r_id})
            if doc['status'] != 'pending':
                print(f"❌ Failed! Reminder processed too early! Status: {doc['status']}")
                return False
            print("✅ Status is still 'pending'. Waiting...")
            
            # 4. Wait until remind_at passed (45s total wait from start)
            # We slept 5s. Wait another 60s (total 65s) to guarantee poll cycle.
            print("⏳ Waiting 60s for poll cycle...")
            time.sleep(60)
            
            # 5. Check FINAL status (should be completed)
            doc = collection.find_one({"_id": r_id})
            print(f"✅ Final Status: {doc['status']}")
            
            if doc['status'] == 'completed':
                print("✅ Timezone Wait Test Passed!")
                return True
            else:
                print(f"❌ Timezone Wait Failed! Status is {doc['status']}")
                return False
                
        finally:
            poller_process.terminate()
            try:
                poller_process.wait(timeout=5)
            except:
                poller_process.kill()

if __name__ == "__main__":
    if not verify_timezone_wait():
        sys.exit(1)
    print("\n🎉 STEP 10 PASSED")