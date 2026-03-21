import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class Config:
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = "asta_db"
    COLLECTION_NAME = "reminders"
    # Poller config
    POLLING_ENABLED = os.getenv("POLLING_ENABLED", "true").lower() == "true"
    DEBUG_POLLING = os.getenv("DEBUG_POLLING", "false").lower() == "true"
    # Using a fast model for latency
    MODEL_NAME = "llama-3.3-70b-versatile"

    def validate(self):
        """
        Validate critical environment variables.
        """
        missing = []
        if not self.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")
        if not self.DEEPGRAM_API_KEY:
            missing.append("DEEPGRAM_API_KEY")
        if not self.MONGO_URI:
            missing.append("MONGO_URI")
            
        if missing:
            logger.warning(f"Missing config for: {', '.join(missing)}. App might not work correctly.")
            # Depending on strictness, we could raise error here.
            # raise ValueError(f"Missing config: {missing}")

config = Config()
