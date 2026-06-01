"""
Unified Database Manager for ASTA.

Single-source-of-truth for all database connections: MongoDB (Motor async) and Neo4j (async).
All MongoDB operations in the entire codebase MUST go through db_manager.
No PyMongo sync clients. No duplicate Motor clients. One pool. One health flag.
"""

import logging
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from neo4j import AsyncGraphDatabase
from typing import Optional, Any, Awaitable, Callable, TypeVar
from backend.app.config import settings

logger = logging.getLogger("DatabaseManager")

T = TypeVar("T")


class DatabaseManager:
    """
    Singleton database manager.
    
    Provides:
      - One Motor async client for MongoDB (pool: 5-50 connections)
      - One async Neo4j driver
      - Unified degraded_mode flag
      - Helper methods for safe collection access with retry
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance.mongo_client: Optional[AsyncIOMotorClient] = None
            cls._instance.neo4j_driver = None
            cls._instance.db = None
            cls._instance.degraded_mode: bool = False
        return cls._instance

    async def connect(self):
        """Initializes and binds singleton database pools."""
        # 1. MongoDB Connection — single Motor client, explicit pool sizing
        try:
            mongo_uri = getattr(settings, "MONGO_URI", None)
            if not mongo_uri:
                logger.error("[DatabaseManager] MONGO_URI is missing from configurations.")
                self.mongo_client = None
                self.db = None
                self.degraded_mode = True
            else:
                self.mongo_client = AsyncIOMotorClient(
                    mongo_uri,
                    maxPoolSize=50,
                    minPoolSize=5,
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=30000,
                    maxIdleTimeMS=45000,
                    tlsAllowInvalidCertificates=True,
                    retryWrites=True,
                    retryReads=True,
                    waitQueueTimeoutMS=10000,
                )
                self.db = self.mongo_client[settings.DB_NAME]
                self.degraded_mode = False
                logger.info("[DatabaseManager] MongoDB Motor client initialized (pool: 5-50).")
        except Exception as e:
            logger.critical(f"[DatabaseManager] Failed to connect to MongoDB: {e}")
            self.mongo_client = None
            self.db = None
            self.degraded_mode = True

        # 2. Neo4j Aura Connection
        try:
            neo4j_uri = getattr(settings, "NEO4J_URI", None)
            neo_user = getattr(settings, "NEO4J_USERNAME", None)
            neo_pass = getattr(settings, "NEO4J_PASSWORD", None)

            if not all([neo4j_uri, neo_user, neo_pass]):
                logger.warning("[DatabaseManager] Neo4j Aura credentials missing. Skipping Graph Layer.")
            else:
                self.neo4j_driver = AsyncGraphDatabase.driver(
                    neo4j_uri, auth=(neo_user, neo_pass), connection_timeout=5.0
                )
                logger.info("[DatabaseManager] Neo4j Aura Graph Database bindings initialized.")
        except Exception as e:
            logger.critical(f"[DatabaseManager] Failed to connect to Neo4j: {e}")
            raise e

        # 3. Ensure indexes on sessions collection
        if self.db is not None:
            await self._ensure_indexes()

    async def _ensure_indexes(self):
        """Create required indexes (idempotent, safe on every startup)."""
        try:
            sessions = self.db[settings.SESSIONS_COLLECTION]

            await sessions.create_index([("session_id", ASCENDING)], unique=True, name="session_id_unique")
            await sessions.create_index([("status", ASCENDING)], name="status_idx")
            await sessions.create_index([("created_at", ASCENDING)], name="created_at_idx")
            await sessions.create_index([("updated_at", ASCENDING)], name="updated_at_idx")
            await sessions.create_index([("last_message_at", ASCENDING)], name="last_message_at_idx")
            await sessions.create_index([("topic", ASCENDING)], name="topic_idx")
            await sessions.create_index([("relevance_score", ASCENDING)], name="relevance_score_idx")
            await sessions.create_index(
                [("pinned", ASCENDING), ("updated_at", ASCENDING)], name="pinned_updated_idx"
            )
            await sessions.create_index(
                [("archived", ASCENDING), ("updated_at", ASCENDING)], name="archived_updated_idx"
            )
            await sessions.create_index([("priority", ASCENDING)], name="priority_idx")
            await sessions.create_index(
                [("status", ASCENDING), ("updated_at", ASCENDING)], name="status_updated_at_idx"
            )

            ttl_days = int(getattr(settings, "SESSION_TTL_DAYS", 30))
            if ttl_days > 0:
                await sessions.create_index(
                    [("ended_at", ASCENDING)],
                    expireAfterSeconds=ttl_days * 24 * 60 * 60,
                    partialFilterExpression={"status": "completed"},
                    name="completed_sessions_ttl",
                )

            logger.info("[DatabaseManager] Session indexes ensured.")
        except Exception as e:
            logger.error(f"[DatabaseManager] Index creation failed: {e}")

    def get_collection(self, collection_name: str):
        """Get a Motor async collection by name. Raises if not connected."""
        if self.db is None:
            raise RuntimeError(f"[DatabaseManager] Database not connected. Cannot get collection '{collection_name}'.")
        return self.db[collection_name]

    async def with_collection(
        self,
        collection_name: str,
        fn: Callable,
        retries: int = 2,
    ) -> Optional[T]:
        """
        Execute an operation against a named collection with retry logic.
        
        The callback `fn` receives the collection and should return an awaitable or value.
        Example:
            result = await db_manager.with_collection("sessions",
                lambda c: c.find_one({"session_id": sid})
            )
        """
        for attempt in range(retries):
            if self.db is None:
                self.degraded_mode = True
                continue

            try:
                collection = self.db[collection_name]
                result = fn(collection)
                if isinstance(result, Awaitable):
                    result = await result
                self.degraded_mode = False
                return result
            except Exception as exc:
                self.degraded_mode = True
                logger.warning(
                    "[DatabaseManager] with_collection(%s) failed (attempt %s/%s): %s",
                    collection_name, attempt + 1, retries, exc,
                )

        return None

    async def ping(self) -> bool:
        """Executes startup life-cycle sanity checks."""
        health = True

        # Ping Mongo
        if self.mongo_client:
            try:
                await self.mongo_client.admin.command("ping")
                self.degraded_mode = False
                logger.info("✔️  MongoDB Health Check: Passed")
            except Exception as e:
                logger.error(f"❌ MongoDB Network Timeout or Auth Failure: {e}")
                self.degraded_mode = True
                health = False
        else:
            self.degraded_mode = True
            health = False

        # Ping Neo4j
        if self.neo4j_driver:
            try:
                await self.neo4j_driver.verify_connectivity()
                logger.info("✔️  Neo4j Aura Health Check: Passed")
            except Exception as e:
                logger.error(f"❌ Neo4j Authentication Error or Instance Unavailable: {e}")
                health = False

        return health

    async def disconnect(self):
        """Graceful shutdown of all database connections."""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("[DatabaseManager] MongoDB connection pool closed.")
        if self.neo4j_driver:
            await self.neo4j_driver.close()
            logger.info("[DatabaseManager] Neo4j bindings shutdown.")


db_manager = DatabaseManager()
