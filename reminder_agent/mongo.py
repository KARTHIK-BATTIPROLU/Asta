from pymongo import MongoClient, ReturnDocument
from datetime import datetime, timedelta, timezone
from .config import config, logger
from bson import ObjectId

class MongoHandler:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self.connect()

    def connect(self):
        try:
            self.client = MongoClient(config.MONGO_URI)
            self.db = self.client[config.DB_NAME]
            self.collection = self.db[config.COLLECTION_NAME]
            
            # Ensure indexes
            self.collection.create_index([("status", 1), ("remind_at", 1)])
            self.collection.create_index([("created_at", -1)])
            
            # Ping
            self.client.admin.command('ping')
            logger.info("MongoDB connected")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e

    def get_due_reminders(self):
        """
        Fetch reminders that are 'pending' and remind_at <= now (UTC).
        """
        now_utc = datetime.now(timezone.utc)
        query = {
            "status": "pending",
            "remind_at": {"$lte": now_utc}
        }
        try:
            reminders = list(self.collection.find(query))
            if reminders:
                logger.info(f"Found {len(reminders)} due reminders.")
            return reminders
        except Exception as e:
            logger.error(f"Error fetching due reminders: {e}")
            return []

    def claim_reminder(self, reminder_id):
        """
        Atomically transition status from 'pending' -> 'sending'.
        Prevents duplicate processing.
        """
        try:
            return self.collection.find_one_and_update(
                {"_id": ObjectId(reminder_id), "status": "pending"},
                {"$set": {"status": "sending", "claimed_at": datetime.now(timezone.utc)}},
                return_document=ReturnDocument.AFTER
            )
        except Exception as e:
            logger.error(f"Error claiming reminder {reminder_id}: {e}")
            return None

    def fail_reminder(self, reminder_id):
        """
        Mark as failed (or revert to pending with retry count).
        """
        try:
            self.collection.update_one(
                {"_id": ObjectId(reminder_id)},
                {"$set": {"status": "failed", "failed_at": datetime.now(timezone.utc)}}
            )
            logger.info(f"Marked reminder {reminder_id} as failed.")
        except Exception as e:
            logger.error(f"Error failing reminder {reminder_id}: {e}")

    def recover_stale_reminders(self):
        """
        Find reminders stuck in 'sending' for > STALE_TIMEOUT.
        Reset status to 'pending'.
        """
        threshold = datetime.now(timezone.utc) - timedelta(seconds=config.STALE_TIMEOUT)
        query = {
            "status": "sending",
            "claimed_at": {"$lte": threshold}
        }
        update = {
            "$set": {"status": "pending", "recovered_at": datetime.now(timezone.utc)}
        }
        try:
            result = self.collection.update_many(query, update)
            if result.modified_count > 0:
                logger.warning(f"Recovered {result.modified_count} stale reminders.")
            return result.modified_count
        except Exception as e:
            logger.error(f"Error recovering stale reminders: {e}")
            return 0

    def mark_completed(self, reminder_id):
        """
        Mark reminder as 'completed'.
        """
        try:
            self.collection.update_one(
                {"_id": ObjectId(reminder_id)},
                {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
            )
            logger.info(f"Marked reminder {reminder_id} as completed.")
        except Exception as e:
            logger.error(f"Error marking reminder {reminder_id} as completed: {e}")

mongo_handler = MongoHandler()