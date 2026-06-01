import os
import logging
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    # Core API Keys
    GROQ_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    MONGO_URI: str = "mongodb://localhost:27017"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "asta-memory"
    NOTION_API_KEY: str = ""
    NOTION_RESEARCH_DB: str = ""
    NOTION_CONTENT_DB: str = ""
    NOTION_YOUTUBE_DB: str = ""
    NOTION_ROUTINE_DB: str = ""
    NEO4J_URI: str = ""
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"
    ANTHROPIC_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = "a08686f9b036609612801c0ef14236ce"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    SERPER_API: str = ""
    
    # Memory Layer Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_HOT: int = 3600          # 1 hour for active session cache
    REDIS_TTL_PREFETCH: int = 1800     # 30 min for pre-fetched context
    REDIS_TTL_ENTITY: int = 86400      # 24 hours for entity cache
    
    MEMORY_TOP_K_SESSIONS: int = 3     # how many past sessions to inject
    MEMORY_CLUSTER_DEPTH: int = 2      # Neo4j traversal depth for clusters
    MEMORY_PREFETCH_ENABLED: bool = True
    
    SESSION_TRANSCRIPT_TTL_DAYS: int = 90  # delete raw transcripts after 90 days
    
    # Timeouts
    EXTERNAL_TIMEOUT_SECONDS: int = 20
    AGENT_TIMEOUT_SECONDS: int = 25
    STT_TIMEOUT_SECONDS: int = 25
    TTS_TIMEOUT_SECONDS: int = 25
    
    # JWT Configuration
    ASTA_JWT_SECRET: str = "change-me-in-production"
    ASTA_JWT_TOKEN: str = "asta-dev-token-change-in-production"  # this is the single user's static token
    
    # WebSocket API Key (optional - if not set, no auth required)
    API_KEY: str = ""
    
    DB_NAME: str = "asta_db"
    COLLECTION_NAME: str = "reminders"
    ROUTINES_COLLECTION: str = "reminders"
    SESSIONS_COLLECTION: str = "sessions"
    ANALYTICS_COLLECTION: str = "analytics"
    PREFERENCES_COLLECTION: str = "preferences"
    # Poller config
    POLLING_ENABLED: bool = True
    DEBUG_POLLING: bool = False
    MODEL_NAME: str = "llama-3.3-70b-versatile"
    
    # Telegram Config
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    POLL_INTERVAL: int = 10  # Seconds
    STALE_TIMEOUT: int = 300 # Seconds
    MAX_AUDIO_BYTES: int = 10 * 1024 * 1024
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 20
    RATE_COOLDOWN_SECONDS: int = 20
    NOISE_SUPPRESSION_ENABLED: bool = True
    REQUEST_QUEUE_MAXSIZE: int = 1000
    REQUEST_QUEUE_WORKERS: int = 12
    MAX_CONCURRENT_FFMPEG: int = 20
    SESSION_TTL_DAYS: int = 30
    ACTIVE_SESSION_TTL_SECONDS: int = 1200
    RETRIEVAL_TIMEOUT_SECONDS: float = 2.0
    SERVICE_TIMEOUT_SECONDS: float = 2.0
    CACHE_TTL_SECONDS: int = 300
    SESSION_CACHE_TTL_SECONDS: int = 900
    SESSION_LRU_MAX_SIZE: int = 100
    DISTRIBUTED_TASKS_ENABLED: bool = False
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    CLEANUP_RETENTION_DAYS: int = 30
    CLEANUP_LOW_PRIORITY_THRESHOLD: float = 0.25
    CLEANUP_INTERVAL_SECONDS: int = 86400
    STT_CONFIDENCE_THRESHOLD: float = 0.60
    SILENCE_TIMEOUT_SECONDS: float = 5.0
    AUTO_PAUSE_ON_SILENCE: bool = True
    INTERRUPTION_THRESHOLD: float = 0.50
    INTERRUPTION_THRESHOLD_AGGRESSIVE: float = 0.35
    INTERRUPTION_THRESHOLD_BALANCED: float = 0.50
    INTERRUPTION_THRESHOLD_STRICT: float = 0.70

    # Routine Agent Integrations
    GOOGLE_CALENDAR_ID: str = "primary"
    GOOGLE_SA_KEY_PATH: str = ""
    
    # Notion Database IDs
    NOTION_DATABASE_ID: str = ""
    NOTION_DEVELOPER_DB: str = ""
    
    # Alias for compatibility
    NOTION_API_TOKEN: str = ""

    # Pinecone Vector Database
    PINECONE_EMBEDDING_DIM: int = 384
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Wake Word Detection
    WAKE_WORD_ENABLED: bool = False
    WAKE_WORD_MODELS: str = "hey_jarvis"
    WAKE_WORD_THRESHOLD: float = 0.5
    WAKE_WORD_COOLDOWN: float = 2.0

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from environment

    def __post_init__(self):
        # Set up compatibility aliases
        self.NOTION_API_TOKEN = self.NOTION_API_KEY
        if not self.CELERY_BROKER_URL and self.REDIS_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL.replace("/0", "/0")
        if not self.CELERY_RESULT_BACKEND and self.REDIS_URL:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL.replace("/0", "/1")

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

settings = Settings()

# Compatibility alias for existing code
config = settings
