import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env
load_dotenv()

class Config:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = "asta_db"
    COLLECTION_NAME = "reminders"
    
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    
    POLL_INTERVAL = 10  # Seconds
    STALE_TIMEOUT = 300 # Seconds

    def validate(self):
        if not self.TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN is missing!")
            raise ValueError("TELEGRAM_TOKEN is missing!")
        if not self.TELEGRAM_CHAT_ID:
            logger.error("TELEGRAM_CHAT_ID is missing!")
            raise ValueError("TELEGRAM_CHAT_ID is missing!")
        if not self.MONGO_URI:
            logger.error("MONGO_URI is missing!")
            raise ValueError("MONGO_URI is missing!")

config = Config()