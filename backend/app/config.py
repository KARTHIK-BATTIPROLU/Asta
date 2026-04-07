import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class Config:
    API_KEY = os.getenv("API_KEY", "").strip()
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = "asta_db"
    COLLECTION_NAME = "reminders"
    ROUTINES_COLLECTION = os.getenv("ROUTINES_COLLECTION", COLLECTION_NAME)
    SESSIONS_COLLECTION = "sessions"
    ANALYTICS_COLLECTION = os.getenv("ANALYTICS_COLLECTION", "analytics")
    PREFERENCES_COLLECTION = os.getenv("PREFERENCES_COLLECTION", "preferences")
    # Poller config
    POLLING_ENABLED = os.getenv("POLLING_ENABLED", "true").lower() == "true"
    DEBUG_POLLING = os.getenv("DEBUG_POLLING", "false").lower() == "true"
    # Using a fast model for latency
    MODEL_NAME = "llama-3.3-70b-versatile"
    
    # Telegram Config
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    
    POLL_INTERVAL = 10  # Seconds
    STALE_TIMEOUT = 300 # Seconds
    EXTERNAL_TIMEOUT_SECONDS = float(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "20"))
    AGENT_TIMEOUT_SECONDS = float(os.getenv("AGENT_TIMEOUT_SECONDS", "45"))
    STT_TIMEOUT_SECONDS = float(os.getenv("STT_TIMEOUT_SECONDS", "25"))
    TTS_TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT_SECONDS", "25"))
    MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(10 * 1024 * 1024)))
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    RATE_COOLDOWN_SECONDS = int(os.getenv("RATE_COOLDOWN_SECONDS", "20"))
    NOISE_SUPPRESSION_ENABLED = os.getenv("NOISE_SUPPRESSION_ENABLED", "true").lower() == "true"
    REQUEST_QUEUE_MAXSIZE = int(os.getenv("REQUEST_QUEUE_MAXSIZE", "1000"))
    REQUEST_QUEUE_WORKERS = int(os.getenv("REQUEST_QUEUE_WORKERS", "12"))
    MAX_CONCURRENT_FFMPEG = int(os.getenv("MAX_CONCURRENT_FFMPEG", "20"))
    SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
    ACTIVE_SESSION_TTL_SECONDS = int(os.getenv("ACTIVE_SESSION_TTL_SECONDS", "1200"))
    RETRIEVAL_TIMEOUT_SECONDS = float(os.getenv("RETRIEVAL_TIMEOUT_SECONDS", "2.0"))
    SERVICE_TIMEOUT_SECONDS = float(os.getenv("SERVICE_TIMEOUT_SECONDS", "2.0"))
    CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))
    SESSION_CACHE_TTL_SECONDS = int(os.getenv("SESSION_CACHE_TTL_SECONDS", "900"))
    SESSION_LRU_MAX_SIZE = int(os.getenv("SESSION_LRU_MAX_SIZE", "100"))
    REDIS_URL = os.getenv("REDIS_URL", "").strip()
    DISTRIBUTED_TASKS_ENABLED = os.getenv("DISTRIBUTED_TASKS_ENABLED", "false").lower() == "true"
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL or "redis://redis:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL or "redis://redis:6379/1")
    CLEANUP_RETENTION_DAYS = int(os.getenv("CLEANUP_RETENTION_DAYS", "30"))
    CLEANUP_LOW_PRIORITY_THRESHOLD = float(os.getenv("CLEANUP_LOW_PRIORITY_THRESHOLD", "0.25"))
    CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "86400"))
    STT_CONFIDENCE_THRESHOLD = float(os.getenv("STT_CONFIDENCE_THRESHOLD", "0.60"))
    SILENCE_TIMEOUT_SECONDS = float(os.getenv("SILENCE_TIMEOUT_SECONDS", "5.0"))
    AUTO_PAUSE_ON_SILENCE = os.getenv("AUTO_PAUSE_ON_SILENCE", "true").lower() == "true"
    INTERRUPTION_THRESHOLD = float(os.getenv("INTERRUPTION_THRESHOLD", "0.50"))
    INTERRUPTION_THRESHOLD_AGGRESSIVE = float(os.getenv("INTERRUPTION_THRESHOLD_AGGRESSIVE", "0.35"))
    INTERRUPTION_THRESHOLD_BALANCED = float(os.getenv("INTERRUPTION_THRESHOLD_BALANCED", "0.50"))
    INTERRUPTION_THRESHOLD_STRICT = float(os.getenv("INTERRUPTION_THRESHOLD_STRICT", "0.70"))

    # Routine Agent Integrations
    GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip()
    GOOGLE_SA_KEY_PATH = os.getenv("GOOGLE_SA_KEY_PATH", "").strip()
    # Notion Config
    NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip()
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()
    # Alias for compatibility if needed
    NOTION_API_TOKEN = NOTION_API_KEY

    # Pinecone Vector Database
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "").strip()
    PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "asta-memory").strip()
    PINECONE_EMBEDDING_DIM = 384
    EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    # Neo4j Aura Graph Database
    NEO4J_URI = os.getenv("NEO4J_URI", "").strip()
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j").strip()
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "").strip()

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
