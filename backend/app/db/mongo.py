from pymongo import MongoClient
from backend.app.config import config
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MongoDB:
    client: MongoClient = None
    db = None
    collection = None

    @classmethod
    def connect(cls):
        if cls.client is None:
            try:
                uri = config.MONGO_URI
                if not uri:
                    logger.error("MONGO_URI is not set!")
                    return

                logger.info(f"Connecting to MongoDB at {uri.split('@')[-1] if '@' in uri else 'localhost'}...")
                cls.client = MongoClient(uri)
                cls.db = cls.client[config.DB_NAME]
                cls.collection = cls.db[config.COLLECTION_NAME]
                
                # Test connection
                cls.client.admin.command('ping')
                logger.info("Connected to MongoDB successfully.")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                # We might want to raise here or handle gracefully, 
                # but for simplicity let's log and continue
                
    @classmethod
    def insert_reminder(cls, reminder_data: dict):
        if cls.collection is None:
            cls.connect()
        if cls.collection is not None:
             return cls.collection.insert_one(reminder_data)
        else:
             logger.error("Database not connected. Cannot insert reminder.")
             return None

# Initialize connection on import or lazily? 
# Usually best to connect on app startup in main.py, but lazy is fine for now.
