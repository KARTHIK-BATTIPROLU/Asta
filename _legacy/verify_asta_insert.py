import datetime
from datetime import timezone
import os
import sys
import pytz
from pymongo import MongoClient
from dotenv import load_dotenv

# Ensure we can import backend
sys.path.append(os.getcwd())

from backend.app.tools.reminder import create_reminder
from backend.app.config import config

load_dotenv()

MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_NAME = config.COLLECTION_NAME

def verify_asta_insert():
    print("\n--- STEP 4: ASTA INSERT VALIDATION ---")
    
    # 1. Invoke Tool
    print("🤖 Calling tool: create_reminder('Verification Reminder', 'in 1 minute')")
    
    try:
        # Note: Tool output depends on current time
        response = create_reminder.invoke({"text": "Verification Reminder", "time": "in 1 minute"})
        print(f"✅ Tool Response: {response}")
        
        if "(IST)" not in response:
            print("❌ Response missing IST indicator!")
            return False
            
    except Exception as e:
        print(f"❌ Tool Invocation Failed: {e}")
        return False

    # 2. Verify Database
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # Find the specific reminder
    # Sort by created_at desc to find latest
    doc = collection.find_one({"text": "Verification Reminder"}, sort=[("created_at", -1)])
    
    if not doc:
        print("❌ Reminder NOT found in Database!")
        return False
        
    print(f"✅ Found Doc ID: {doc['_id']}")
    
    stored_time = doc['remind_at']
    print(f"   Stored Time (UTC): {stored_time} (Type: {type(stored_time)})")
    
    # Verify UTC
    if stored_time.tzinfo != timezone.utc:
        # Pymongo might return naive datetime in UTC. That's actually OK if we treat it as UTC.
        # But let's check if it's close to current UTC+1min.
        # If naive, assume UTC.
        stored_time = stored_time.replace(tzinfo=timezone.utc)
    
    now_utc = datetime.datetime.now(timezone.utc)
    diff = (stored_time - now_utc).total_seconds()
    
    print(f"   Time Delta (s): {diff}")
    
    if 50 < diff < 70: # Expect ~60s
        print("✅ Time is correctly ~60s in future (UTC)")
        
        # Cleanup
        collection.delete_one({"_id": doc['_id']})
        print("✅ Cleaned up Verification Reminder")
        return True
    else:
        print(f"❌ Time Delta unexpected! Expected ~60s, got {diff}s")
        return False

if __name__ == "__main__":
    if not verify_asta_insert():
        sys.exit(1)
    print("\n🎉 STEP 4 PASSED")