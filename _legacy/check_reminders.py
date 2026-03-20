from pymongo import MongoClient
from datetime import datetime, timezone
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["asta_db"]
collection = db["reminders"]

print("--- PENDING REMINDERS ---")
for doc in collection.find({"status": "pending"}):
    print(f"ID: {doc['_id']} | Text: {doc.get('text')} | RemindAt: {doc.get('remind_at')}")

print("\n--- ALL REMINDERS (Count) ---")
print(collection.count_documents({}))
