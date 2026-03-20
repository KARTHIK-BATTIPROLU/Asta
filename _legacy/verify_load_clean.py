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

def verify_load_clean():
    print("\n--- STEP 11: CLEAN LOAD TEST (50 Reminders) ---")
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # 0. Clean DB
    print("🧹 Cleaning database...")
    collection.delete_many({})
    print("✅ Database cleared.")
    
    # 1. Insert 50 reminders
    count = 50
    print(f"📥 Inserting {count} reminders...")
    
    docs = []
    now = datetime.datetime.now(timezone.utc)
    for i in range(count):
        docs.append({
            "text": f"Load Test #{i+1} 🚀", # Unique text per item
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
    
    # Ensure UTF-8 output capture & Unbuffered
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    
    # Redirect output to file to avoid pipe buffer deadlocks
    with open("poller_load_test.log", "w", encoding="utf-8") as log_file:
        poller_process = subprocess.Popen(
            [sys.executable, "-m", "reminder_agent.poller"],
            stdout=log_file,
            stderr=subprocess.STDOUT, # Merge stderr to stdout
            text=True,
            encoding='utf-8',
            env=env
        )
        
        # 3. Wait/Monitor progress
        # Check every 5s until done or timeout (180s due to API latency)
        timeout = 180
        success = False
        
        try:
            while time.time() - start_time < timeout:
                processed = collection.count_documents({
                    "_id": {"$in": ids},
                    "status": {"$in": ["completed", "failed"]}
                })
                
                elapsed = time.time() - start_time
                print(f"📊 Progress: {processed}/{count} ({int(processed/count*100)}%) - {elapsed:.1f}s")
                
                if processed == count:
                    print(f"✅ Load Test Passed! Processed {count} in {elapsed:.2f}s")
                    success = True
                    break
                    
                time.sleep(5)
                
            if not success:
                print(f"❌ Load Test Failed! Timeout after {timeout}s. Processed {processed}/{count}.")
                
        except Exception as e:
            print(f"❌ Exception during test: {e}")
            poller_process.kill()
        finally:
            if poller_process.poll() is None:
                poller_process.terminate()
                try:
                    poller_process.wait(timeout=5)
                except:
                    poller_process.kill()
            
            # Print log summary on failure
            if not success:
                print("\n📝 Poller Log Tail (Last 20 lines):")
                # Read from the file we just wrote
                try:
                    with open("poller_load_test.log", "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        print("".join(lines[-20:]))
                except Exception as e:
                    print(f"Could not read log file: {e}")

    return success

if __name__ == "__main__":
    if not verify_load_clean():
        sys.exit(1)
    print("\n🎉 STEP 11 PASSED")