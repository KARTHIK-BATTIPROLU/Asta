from pymongo import MongoClient
from datetime import datetime, timezone
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["asta_db"]
collection = db["reminders"]

now_utc = datetime.now(timezone.utc)
query = {
    "status": "pending",
    "remind_at": {"$lte": now_utc}
}

print(f"Querying with now_utc: {now_utc}")
reminders = list(collection.find(query))
print(f"Found {len(reminders)} reminders.")

for r in reminders:
    print(f"ID: {r['_id']} | RemindAt: {r['remind_at']} | Type: {type(r['remind_at'])}")
    if r['remind_at'].tzinfo is None:
        print("  -> WARNING: Naive datetime stored!")
    else:
        print(f"  -> Aware: {r['remind_at'].tzinfo}")
