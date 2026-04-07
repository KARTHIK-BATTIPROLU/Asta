from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional, TypeVar
import importlib

try:
    AsyncIOMotorClient = importlib.import_module("motor.motor_asyncio").AsyncIOMotorClient
except Exception:
    AsyncIOMotorClient = None

from backend.app.config import config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncMongoDB:
    """Async MongoDB access layer for high-concurrency paths."""

    client: Optional[Any] = None
    db = None
    degraded_mode: bool = False

    @classmethod
    async def connect(cls):
        if cls.client is not None:
            return

        try:
            if AsyncIOMotorClient is None:
                logger.warning("[ASYNC_MONGO] motor is not installed; async DB path disabled")
                cls.degraded_mode = True
                return
            if not config.MONGO_URI:
                logger.error("[ASYNC_MONGO] MONGO_URI is not set")
                cls.degraded_mode = True
                return

            cls.client = AsyncIOMotorClient(
                config.MONGO_URI,
                maxPoolSize=80,
                minPoolSize=5,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
                retryWrites=True,
            )
            cls.db = cls.client[config.DB_NAME]
            await cls.client.admin.command("ping")
            cls.degraded_mode = False
            logger.info("[ASYNC_MONGO] Connected")
        except Exception as exc:
            logger.warning("[ASYNC_MONGO] connect failed: %s", exc)
            cls.degraded_mode = True

    @classmethod
    async def get_collection(cls, name: str):
        if cls.db is None:
            await cls.connect()
        if cls.db is None:
            return None

        try:
            await cls.client.admin.command("ping")
            cls.degraded_mode = False
            return cls.db[name]
        except Exception as exc:
            logger.warning("[ASYNC_MONGO] health check failed: %s", exc)
            cls.degraded_mode = True
            return None

    @classmethod
    async def with_collection(
        cls,
        name: str,
        fn: Callable,
        retries: int = 2,
    ) -> Optional[T]:
        for attempt in range(retries):
            collection = await cls.get_collection(name)
            if collection is None:
                continue

            try:
                result = fn(collection)
                if isinstance(result, Awaitable):
                    result = await result
                cls.degraded_mode = False
                return result
            except Exception as exc:
                cls.degraded_mode = True
                logger.warning(
                    "[ASYNC_MONGO] operation failed (attempt %s/%s): %s",
                    attempt + 1,
                    retries,
                    exc,
                )

        return None

    @classmethod
    async def close(cls):
        if cls.client is not None:
            cls.client.close()
        cls.client = None
        cls.db = None
