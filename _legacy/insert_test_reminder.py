from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

def create_test_data():
    client = MongoClient(MONGO_URI)
    db = client["asta_db"]
    collection = db["reminders"]
    
    for i in range(1, 11):
        reminder = {
            "text": f"Test Reminder {i} 🔔",
            "remind_at": datetime.now(timezone.utc),
            "status": "pending",
            "created_at": datetime.now(timezone.utc)
        }
        
        res = collection.insert_one(reminder)
        print(f"Inserted Test Reminder {i}: {res.inserted_id}")
    
    print("✅ Inserted 10 reminders successfully!")

if __name__ == "__main__":
    create_test_data()