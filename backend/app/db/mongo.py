from pymongo import ASCENDING, MongoClient
from backend.app.config import config
from backend.app.db.mongo_hardening import (
    POOL_CONFIG, build_connection_uri, MongoHealthCheck,
    get_collection_safe, retry_on_db_failure, log_pool_stats
)
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MongoDB:
    client: MongoClient = None
    db = None
    collection = None
    degraded_mode: bool = False

    @classmethod
    def connect(cls):
        if cls.client is None:
            try:
                uri = config.MONGO_URI
                if not uri:
                    logger.error("[MONGO] MONGO_URI is not set!")
                    return

                # Build URI with replica set support ONLY if not Atlas cluster
                if "mongodb.net" not in uri:
                    uri = build_connection_uri(uri, include_replica_set=True)
                else:
                    uri = build_connection_uri(uri, include_replica_set=False)
                
                logger.info(f"[MONGO] Connecting to MongoDB (pool_size=5-50, replica_set support)...")
                
                # Create client with production-grade connection pooling
                cls.client = MongoClient(uri, **POOL_CONFIG)
                
                # Register health check
                MongoHealthCheck.client = cls.client
                
                cls.db = cls.client[config.DB_NAME]
                cls.collection = cls.db[config.COLLECTION_NAME]
                cls.ensure_session_indexes()
                
                # Perform health check
                if MongoHealthCheck.is_db_alive():
                    cls.degraded_mode = False
                    logger.info("[MONGO] Connected to MongoDB successfully with pooling enabled")
                    log_pool_stats(cls.client)
                else:
                    cls.degraded_mode = True
                    logger.warning("[MONGO] Connected but health check failed - may recover automatically")
                    
            except Exception as e:
                logger.error(f"[MONGO] Failed to connect to MongoDB: {type(e).__name__}: {str(e)[:150]}")
                MongoHealthCheck.is_connected = False
                cls.degraded_mode = True
                # Connection is attempted again on next operation

    @classmethod
    def safe_db_call(cls, fn, retries: int = 2):
        """
        Safe DB call wrapper with retry and degraded fallback.
        Returns None when persistent DB failures occur.
        """
        for attempt in range(retries):
            try:
                result = fn()
                cls.degraded_mode = False
                return result
            except Exception as e:
                cls.degraded_mode = True
                logger.warning("[MONGO_SAFE] DB call failed (attempt %s/%s): %s", attempt + 1, retries, e)
        logger.warning("[MONGO_SAFE] Entering degraded mode - DB unavailable")
        return None

    @classmethod
    def ensure_session_indexes(cls):
        """
        Ensure required session indexes exist for fast recovery/finalization queries.
        Index creation is idempotent and safe to run on every startup.
        """
        if cls.db is None:
            logger.warning("[MONGO_IDX] Database not initialized, cannot create indexes")
            return

        try:
            sessions = cls.db[config.SESSIONS_COLLECTION]
            
            logger.debug("[MONGO_IDX] Creating session indexes...")
            sessions.create_index([("session_id", ASCENDING)], unique=True, name="session_id_unique")
            sessions.create_index([("status", ASCENDING)], name="status_idx")
            sessions.create_index([("created_at", ASCENDING)], name="created_at_idx")
            sessions.create_index([("updated_at", ASCENDING)], name="updated_at_idx")
            sessions.create_index([("last_message_at", ASCENDING)], name="last_message_at_idx")
            sessions.create_index([("topic", ASCENDING)], name="topic_idx")
            sessions.create_index([("relevance_score", ASCENDING)], name="relevance_score_idx")
            sessions.create_index([("pinned", ASCENDING), ("updated_at", ASCENDING)], name="pinned_updated_idx")
            sessions.create_index([("archived", ASCENDING), ("updated_at", ASCENDING)], name="archived_updated_idx")
            sessions.create_index([("priority", ASCENDING)], name="priority_idx")

            # Optimizes: find(status="finalizing").sort(updated_at).limit(batch_size)
            sessions.create_index([("status", ASCENDING), ("updated_at", ASCENDING)], name="status_updated_at_idx")

            ttl_days = int(getattr(config, "SESSION_TTL_DAYS", 30))
            if ttl_days > 0:
                sessions.create_index(
                    [("ended_at", ASCENDING)],
                    expireAfterSeconds=ttl_days * 24 * 60 * 60,
                    partialFilterExpression={"status": "completed"},
                    name="completed_sessions_ttl",
                )
                logger.debug(f"[MONGO_IDX] TTL index set for {ttl_days} days")

            logger.info("[MONGO_IDX] Session indexes ensured successfully")
            
        except Exception as e:
            logger.error(f"[MONGO_IDX] Failed to ensure indexes: {type(e).__name__}: {str(e)[:100]}")
            # Continue anyway - indexes may already exist
                
    @classmethod
    def get_collection(cls, name: str):
        """
        Get a specific collection by name with health check.
        
        Ensures connection is established first and performs health check.
        Returns None if database is unavailable to allow graceful degradation.
        """
        if cls.db is None:
            cls.connect()

        if not MongoHealthCheck.is_db_alive():
            cls.degraded_mode = True
            logger.warning("[MONGO] DB health check failed - using degraded mode")
            return None
        
        # Use safe collection access with health check
        collection = get_collection_safe(cls.db, name, health_check=True)
        if collection is None:
            cls.degraded_mode = True
        return collection

    @classmethod
    def insert_reminder(cls, reminder_data: dict):
        """
        Insert a reminder with safe error handling and retry logic.
        """
        if cls.collection is None:
            cls.connect()
        
        if cls.collection is not None:
            try:
                result = cls.safe_db_call(lambda: cls._insert_reminder_with_retry(reminder_data))
                if result is None:
                    return None
                logger.debug(f"[MONGO_OPS] Reminder inserted successfully")
                return result
            except Exception as e:
                logger.error(f"[MONGO_OPS] Failed to insert reminder: {type(e).__name__}: {str(e)[:100]}")
                return None
        else:
            logger.error("[MONGO_OPS] Database not connected. Cannot insert reminder.")
            return None

    @classmethod
    @retry_on_db_failure(max_retries=2, backoff=1.0)
    def _insert_reminder_with_retry(cls, reminder_data: dict):
        """
        Internal method with retry decorator for reminder insertion.
        """
        return cls.collection.insert_one(reminder_data)

    @classmethod
    def insert_routine_task(cls, routine_data: dict):
        """
        Insert a routine task with safe error handling and retry logic.
        """
        collection = cls.get_collection(config.ROUTINES_COLLECTION)
        
        if collection is not None:
            try:
                result = cls.safe_db_call(lambda: cls._insert_routine_task_with_retry(collection, routine_data))
                if result is None:
                    return None
                logger.debug(f"[MONGO_OPS] Routine task inserted successfully")
                return result
            except Exception as e:
                logger.error(f"[MONGO_OPS] Failed to insert routine task: {type(e).__name__}: {str(e)[:100]}")
                return None
        
        logger.error("[MONGO_OPS] Database not connected. Cannot insert routine task.")
        return None

    @classmethod
    @retry_on_db_failure(max_retries=2, backoff=1.0)
    def _insert_routine_task_with_retry(cls, collection, routine_data: dict):
        """
        Internal method with retry decorator for routine task insertion.
        """
        return collection.insert_one(routine_data)
    
    @classmethod
    def is_db_alive(cls) -> bool:
        """
        Check if database is currently alive and responsive.
        
        Returns:
            True if database is reachable, False otherwise
        """
        alive = MongoHealthCheck.is_db_alive()
        cls.degraded_mode = not alive
        return alive

    @classmethod
    def is_degraded(cls) -> bool:
        return cls.degraded_mode

    @classmethod
    def is_connected(cls) -> bool:
        return bool(cls.client is not None and cls.db is not None and cls.is_db_alive())
    
    @classmethod
    def get_pool_status(cls) -> dict:
        """
        Get current connection pool status for monitoring.
        
        Returns:
            Dictionary with pool statistics
        """
        if cls.client is None:
            return {"status": "not_initialized"}
        
        return log_pool_stats(cls.client)

from backend.app.core.interfaces import IDatabase

from backend.app.core.errors import ServiceError

class MongoImpl(IDatabase):
    def get_collection(self, name: str):
        if MongoDB.db is None:
            raise ServiceError("Database not initialized")
        return MongoDB.db[name]

    def is_degraded(self) -> bool:
        return MongoDB.degraded_mode

    def connect(self) -> None:
        MongoDB.connect()
        
    def is_connected(self) -> bool:
        return MongoDB.client is not None

    def close(self) -> None:
        if MongoDB.client:
            MongoDB.client.close()

