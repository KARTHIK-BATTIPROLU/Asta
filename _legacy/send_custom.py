import sys
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

def create_custom_reminder(text):
    client = MongoClient(MONGO_URI)
    db = client["asta_db"]
    collection = db["reminders"]
    
    reminder = {
        "text": text,
        "remind_at": datetime.now(timezone.utc),
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }
    
    res = collection.insert_one(reminder)
    print(f"✅ Queued Custom Notification: '{text}'")
    print(f"   ID: {res.inserted_id}")
    print("   (The Poller agent will send this shortly)")

if __name__ == "__main__":
    print("--- Send Custom Telegram Notification ---")
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
    else:
        print("Usage: python -m reminder_agent.send_custom 'Your message here'")
        message = input("Or enter message now: ")
    
    if message.strip():
        create_custom_reminder(message)
    else:
        print("❌ Error: Message cannot be empty.")