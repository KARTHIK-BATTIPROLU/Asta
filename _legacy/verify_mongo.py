import datetime
from datetime import timezone
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "asta_db"
COLLECTION_NAME = "reminders"

def test_mongo():
    print("\n--- STEP 3: MONGODB TEST ---")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        client.admin.command('ping')
        print("✅ Connected to MongoDB")
        
        # Test Insert
        test_doc = {
            "text": "DB Connectivity Test",
            "created_at": datetime.datetime.now(timezone.utc),
            "status": "connectivity_test"
        }
        res = collection.insert_one(test_doc)
        print(f"✅ Inserted doc ID: {res.inserted_id}")
        
        # Fetch Back
        doc = collection.find_one({"_id": res.inserted_id})
        if doc and doc["text"] == "DB Connectivity Test":
            print("✅ Fetched doc successfully")
            
            # Cleanup
            collection.delete_one({"_id": res.inserted_id})
            print("✅ Cleaned up test doc")
            return True
        else:
            print("❌ Correct document NOT found")
            return False
            
    except Exception as e:
        print(f"❌ MongoDB Error: {e}")
        return False

if __name__ == "__main__":
    if not test_mongo():
        sys.exit(1)
    print("\n🎉 STEP 3 PASSED")