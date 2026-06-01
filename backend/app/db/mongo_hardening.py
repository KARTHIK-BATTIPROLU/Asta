"""
MongoDB Connection Hardening Module for ASTA.

Provides production-grade resilience utilities for the unified db_manager Motor client.
Includes connection pool configuration, health checks, async retry logic, and monitoring.
No PyMongo sync imports. All operations are async-first.
"""

import asyncio
import logging
import time
from typing import Optional, Any, Callable, TypeVar, Dict
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar("T")

# --- CONNECTION POOLING CONFIGURATION ---
# These values are applied in db_manager.connect() via AsyncIOMotorClient kwargs.
POOL_CONFIG = {
    "maxPoolSize": 50,
    "minPoolSize": 5,
    "maxIdleTimeMS": 45000,
    "serverSelectionTimeoutMS": 20000,
    "connectTimeoutMS": 20000,
    "socketTimeoutMS": 30000,
    "retryWrites": True,
    "retryReads": True,
    "waitQueueTimeoutMS": 10000,
}


# --- ASYNC RETRY DECORATOR ---

def async_retry_on_db_failure(max_retries: int = 2, backoff: float = 2.0):
    """
    Async decorator to add retry logic to MongoDB operations.

    Retries on transient errors (connection issues, timeouts).
    Does NOT retry on logical errors.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            attempt = 0
            retry_delay = 0.1  # Start with 100ms

            while attempt <= max_retries:
                try:
                    logger.debug(f"[DB_RETRY] {func.__name__} attempt {attempt + 1}/{max_retries + 1}")
                    result = await func(*args, **kwargs)

                    if attempt > 0:
                        logger.info(f"[DB_RETRY] {func.__name__} succeeded on retry {attempt}")

                    return result

                except Exception as e:
                    err_name = type(e).__name__
                    # Retryable: connection reset, timeout, server selection failures
                    retryable_errors = (
                        "ServerSelectionTimeoutError",
                        "ConnectionFailure",
                        "AutoReconnect",
                        "NetworkTimeout",
                    )
                    is_retryable = err_name in retryable_errors

                    if is_retryable and attempt < max_retries:
                        logger.warning(
                            f"[DB_RETRY] {func.__name__} transient error "
                            f"(attempt {attempt + 1}): {err_name}: {str(e)[:100]}"
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= backoff
                        attempt += 1
                    else:
                        logger.error(
                            f"[DB_RETRY] {func.__name__} failed: "
                            f"{err_name}: {str(e)[:100]}"
                        )
                        raise

            return None
        return wrapper
    return decorator


# --- HEALTH CHECK ---

class MongoHealthCheck:
    """Async health check utilities for the unified Motor client."""

    last_failure_time: Optional[float] = None
    failure_count: int = 0
    is_connected: bool = False
    FAILURE_THRESHOLD = 3
    RECOVERY_WINDOW_SECONDS = 60

    @classmethod
    async def is_db_alive(cls, client) -> bool:
        """Perform an async health check using admin.command('ping')."""
        if client is None:
            logger.warning("[DB_HEALTH] No client available for health check")
            return False

        try:
            await client.admin.command("ping")

            if cls.failure_count > 0:
                logger.info("[DB_HEALTH] Connection restored after failures")
                cls.failure_count = 0

            cls.is_connected = True
            return True

        except Exception as e:
            cls.failure_count += 1
            logger.error(
                f"[DB_HEALTH] Ping failed: {type(e).__name__}: {str(e)[:100]} "
                f"(failures: {cls.failure_count}/{cls.FAILURE_THRESHOLD})"
            )

            if cls.failure_count >= cls.FAILURE_THRESHOLD:
                cls.is_connected = False
                cls.last_failure_time = time.time()

            return False

    @classmethod
    def should_retry_recovery(cls) -> bool:
        """Check if enough time has passed to retry connection recovery."""
        if cls.last_failure_time is None:
            return True
        elapsed = time.time() - cls.last_failure_time
        return elapsed >= cls.RECOVERY_WINDOW_SECONDS


# --- POOL MONITORING ---

async def log_pool_stats(client) -> Dict[str, Any]:
    """Log current connection pool statistics (async-safe)."""
    try:
        stats = {
            "status": "connected" if MongoHealthCheck.is_connected else "disconnected",
            "health_status": (
                "healthy" if MongoHealthCheck.failure_count == 0
                else f"degraded ({MongoHealthCheck.failure_count} failures)"
            ),
        }
        logger.info(f"[DB_POOL] Pool stats: {stats}")
        return stats
    except Exception as e:
        logger.warning(f"[DB_POOL] Could not retrieve pool stats: {type(e).__name__}")
        return {"status": "unknown"}
