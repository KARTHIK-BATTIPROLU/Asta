import time
import sys
import os
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
import dateparser
import pytz

# Load environment
load_dotenv()

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "asta_db"
COLLECTION_NAME = "reminders"
IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc

def connect_db():
    print(f"🔌 Connecting to MongoDB...")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        client.admin.command('ping')
        print("✅ MongoDB Connected")
        return collection
    except Exception as e:
        print(f"❌ MongoDB Connection Failed: {e}")
        sys.exit(1)

def test_input_parsing(input_time_str):
    print(f"\n🔍 Testing Input Parsing: '{input_time_str}'")
    
    settings = {
        'TIMEZONE': 'Asia/Kolkata',
        'RETURN_AS_TIMEZONE_AWARE': True,
        'PREFER_DATES_FROM': 'future'
    }
    parsed_time = dateparser.parse(input_time_str, settings=settings)
    
    if not parsed_time:
        print("❌ Failed to parse time")
        return None

    # Normalization
    if parsed_time.tzinfo is None:
        parsed_time = IST.localize(parsed_time)
    else:
        parsed_time = parsed_time.astimezone(IST)
        
    utc_time = parsed_time.astimezone(UTC)
    
    print(f"   Parsed (IST): {parsed_time}")
    print(f"   Stored (UTC): {utc_time}")
    
    # Validation
    now_utc = datetime.now(timezone.utc)
    if utc_time < now_utc:
        print("⚠️  Warning: Time is in the past (might be intentional for immediate test)")
    
    return utc_time

def insert_test_reminder(collection, text, utc_time):
    reminder = {
        "text": text,
        "remind_at": utc_time,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "test_id": "verify_system_run" # Marker for cleanup
    }
    res = collection.insert_one(reminder)
    print(f"✅ Inserted Reminder: '{text}' (ID: {res.inserted_id})")
    return res.inserted_id

def monitor_reminders(collection, reminder_ids):
    print("\n👀 Monitoring for status updates (Max 60s)...")
    start_time = time.time()
    
    pending = set(reminder_ids)
    
    while pending and (time.time() - start_time) < 60:
        for r_id in list(pending):
            doc = collection.find_one({"_id": r_id})
            status = doc.get("status")
            
            if status == "completed":
                print(f"✅ Reminder {r_id} COMPLETED!")
                pending.remove(r_id)
            elif status == "failed":
                print(f"❌ Reminder {r_id} FAILED!")
                pending.remove(r_id)
            elif status == "sending":
                 print(f"⏳ Reminder {r_id} is SENDING...")
            
        time.sleep(2)
        
    if pending:
        print(f"⚠️  Timed out. Remaining pending/sending: {pending}")
    else:
        print("\n🎉 All test reminders processed successfully!")

def main():
    print("🚀 STARTING SYSTEM VERIFICATION\n")
    collection = connect_db()
    
    # 1. Parsing Test
    utc_immediate = test_input_parsing("in 10 seconds")
    utc_future = test_input_parsing("in 2 minutes")
    
    # 2. Insert Data
    ids = []
    if utc_immediate:
        ids.append(insert_test_reminder(collection, "⚡ Immediate Verification Test", utc_immediate))
    
    # 3. Monitor
    if ids:
        monitor_reminders(collection, ids)

if __name__ == "__main__":
    main()