"""
MongoDB Connection Manager Hardening Module

Provides production-grade MongoDB resilience, pooling, and fault tolerance.
Includes connection pooling configuration, health checks, retry logic, and automatic recovery.
"""

import logging
import time
from typing import Optional, Any, Callable, TypeVar, Dict
from functools import wraps
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure, ConnectionFailure

logger = logging.getLogger(__name__)

T = TypeVar("T")

# --- CONNECTION POOLING CONFIGURATION ---

# Production-grade connection pool settings
POOL_CONFIG = {
    "maxPoolSize": 50,  # Maximum connections in pool
    "minPoolSize": 5,   # Minimum connections to maintain
    "maxIdleTimeMS": 45000,  # Close idle connections after 45s
    "serverSelectionTimeoutMS": 5000,  # 5s to find server
    "connectTimeoutMS": 5000,  # 5s to establish connection
    "socketTimeoutMS": 10000,  # 10s socket timeout
    "retryWrites": True,  # Automatic write retry
    "retryReads": True,  # Automatic read retry (MongoDB 3.6+)
    "waitQueueTimeoutMS": 1000,  # 1s to get connection from pool
}

# Replica set configuration
REPLICA_SET_CONFIG = {
    "replicaSet": "rs0",  # Default replica set name
    "readPreference": "primary",  # Read from primary
}


def build_connection_uri(base_uri: str, include_replica_set: bool = True) -> str:
    """
    Build a properly formatted MongoDB connection URI with replica set support.
    
    Args:
        base_uri: Base MongoDB URI (with or without query params)
        include_replica_set: Whether to add replica set parameter (default: True)
        
    Returns:
        Properly formatted URI with replica set support
    """
    if not base_uri:
        logger.error("[DB_URI] Base URI is empty")
        return base_uri
    
    # If URI already has replicaSet param, don't override
    if "replicaSet=" in base_uri:
        logger.debug("[DB_URI] Replica set already in URI")
        return base_uri
    
    # Add replicaSet parameter if requested
    if include_replica_set and "?" not in base_uri:
        uri = f"{base_uri}/?replicaSet={REPLICA_SET_CONFIG['replicaSet']}"
    elif include_replica_set:
        uri = f"{base_uri}&replicaSet={REPLICA_SET_CONFIG['replicaSet']}"
    else:
        uri = base_uri
    
    logger.debug("[DB_URI] Final URI configured with replica set support")
    return uri


# --- CONNECTION HEALTH CHECK ---

class MongoHealthCheck:
    """Manage MongoDB connection health and automatic recovery."""
    
    client: Optional[MongoClient] = None
    is_connected: bool = False
    last_failure_time: Optional[float] = None
    failure_count: int = 0
    
    FAILURE_THRESHOLD = 3  # Mark unhealthy after 3 consecutive failures
    RECOVERY_WINDOW_SECONDS = 60  # Try recovery every 60s
    
    @classmethod
    def is_db_alive(cls, timeout: int = 2000) -> bool:
        """
        Perform a health check to verify database connectivity.
        
        Uses admin.command("ping") which is lightweight and reliable.
        
        Args:
            timeout: Ping timeout in milliseconds (default: 2000ms)
            
        Returns:
            True if database is reachable, False otherwise
        """
        if cls.client is None:
            logger.warning("[DB_HEALTH] No client available for health check")
            return False
        
        try:
            # Ping with timeout
            cls.client.admin.command(
                "ping",
                maxTimeMSForConnection=timeout,
            )
            
            # Reset failure counter on success
            if cls.failure_count > 0:
                logger.info("[DB_HEALTH] Connection restored after failures")
                cls.failure_count = 0
            
            cls.is_connected = True
            return True
            
        except ServerSelectionTimeoutError:
            cls.failure_count += 1
            logger.warning(f"[DB_HEALTH] Ping timeout (failures: {cls.failure_count}/{cls.FAILURE_THRESHOLD})")
            
        except Exception as e:
            cls.failure_count += 1
            logger.error(f"[DB_HEALTH] Ping failed: {type(e).__name__}: {str(e)[:100]} (failures: {cls.failure_count}/{cls.FAILURE_THRESHOLD})")
        
        # Mark unhealthy after threshold
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


# --- RETRY DECORATOR ---

def retry_on_db_failure(max_retries: int = 2, backoff: float = 1.0):
    """
    Decorator to add retry logic to MongoDB operations.
    
    Retries on transient errors (connection issues, timeouts).
    Does NOT retry on logical errors (invalid queries, etc.).
    
    Args:
        max_retries: Maximum number of retry attempts (default: 2)
        backoff: Backoff multiplier between retries (default: 1.0 = no backoff)
        
    Returns:
        Decorated function that retries on failure
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            retry_delay = 0.1  # Start with 100ms
            
            while attempt <= max_retries:
                try:
                    logger.debug(f"[DB_RETRY] {func.__name__} attempt {attempt + 1}/{max_retries + 1}")
                    result = func(*args, **kwargs)
                    
                    if attempt > 0:
                        logger.info(f"[DB_RETRY] {func.__name__} succeeded on retry {attempt}")
                    
                    return result
                    
                except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                    # Transient connection errors - retry
                    logger.warning(f"[DB_RETRY] {func.__name__} failed with transient error (attempt {attempt + 1}): {type(e).__name__}")
                    
                    if attempt < max_retries:
                        logger.info(f"[DB_RETRY] Retrying after {retry_delay:.2f}s backoff...")
                        time.sleep(retry_delay)
                        retry_delay *= backoff  # Exponential backoff
                        attempt += 1
                    else:
                        logger.error(f"[DB_RETRY] Exhausted retries for {func.__name__}")
                        raise
                        
                except OperationFailure as e:
                    # Operation errors - check if retryable
                    error_code = e.code if hasattr(e, "code") else None
                    
                    # Retryable codes: connection errors, temporary unavailable
                    retryable_codes = [6, 7, 89, 91, 111, 137, 189]
                    
                    if error_code in retryable_codes and attempt < max_retries:
                        logger.warning(f"[DB_RETRY] {func.__name__} failed with retryable code {error_code} (attempt {attempt + 1})")
                        time.sleep(retry_delay)
                        retry_delay *= backoff
                        attempt += 1
                    else:
                        logger.error(f"[DB_RETRY] Non-retryable operation error in {func.__name__}: {str(e)[:100]}")
                        raise
                        
                except Exception as e:
                    # Non-retryable errors (logic errors, etc.)
                    logger.error(f"[DB_RETRY] {func.__name__} failed with non-retryable error: {type(e).__name__}: {str(e)[:100]}")
                    raise
            
            return None  # Should not reach here
        
        return wrapper
    return decorator


# --- SAFE COLLECTION ACCESS ---

def get_collection_safe(db, collection_name: str, health_check: bool = True):
    """
    Safely get a MongoDB collection with optional health check.
    
    Args:
        db: MongoDB database object
        collection_name: Name of collection to retrieve
        health_check: Whether to perform health check first (default: True)
        
    Returns:
        Collection object or None if database is unavailable
    """
    if health_check and not MongoHealthCheck.is_db_alive():
        logger.error(f"[DB_SAFE] Database check failed, cannot get collection {collection_name}")
        return None
    
    if db is None:
        logger.error(f"[DB_SAFE] Database not initialized, cannot get collection {collection_name}")
        return None
    
    try:
        collection = db[collection_name]
        logger.debug(f"[DB_SAFE] Got collection {collection_name}")
        return collection
        
    except Exception as e:
        logger.error(f"[DB_SAFE] Failed to get collection {collection_name}: {type(e).__name__}: {str(e)[:100]}")
        return None


# --- SAFE DB OPERATIONS ---

async def async_retry_on_db_failure(max_retries: int = 2, backoff: float = 1.0):
    """
    Async decorator to add retry logic to MongoDB operations.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 2)
        backoff: Backoff multiplier between retries (default: 1.0)
        
    Returns:
        Decorated async function that retries on failure
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            import asyncio
            
            attempt = 0
            retry_delay = 0.1  # Start with 100ms
            
            while attempt <= max_retries:
                try:
                    logger.debug(f"[DB_ASYNC_RETRY] {func.__name__} attempt {attempt + 1}/{max_retries + 1}")
                    result = await func(*args, **kwargs)
                    
                    if attempt > 0:
                        logger.info(f"[DB_ASYNC_RETRY] {func.__name__} succeeded on retry {attempt}")
                    
                    return result
                    
                except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                    logger.warning(f"[DB_ASYNC_RETRY] {func.__name__} transient error (attempt {attempt + 1}): {type(e).__name__}")
                    
                    if attempt < max_retries:
                        logger.info(f"[DB_ASYNC_RETRY] Retrying after {retry_delay:.2f}s...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= backoff
                        attempt += 1
                    else:
                        logger.error(f"[DB_ASYNC_RETRY] Exhausted retries for {func.__name__}")
                        raise
                        
                except Exception as e:
                    logger.error(f"[DB_ASYNC_RETRY] {func.__name__} failed: {type(e).__name__}: {str(e)[:100]}")
                    raise
            
            return None
        
        return wrapper
    return decorator


# --- CONECTION POOL MONITORING ---

def log_pool_stats(client: MongoClient) -> Dict[str, Any]:
    """
    Log current connection pool statistics for monitoring.
    
    Args:
        client: MongoDB client
        
    Returns:
        Dictionary with pool statistics
    """
    try:
        # Get pool options
        options = client._topology
        
        stats = {
            "servers": len(options.server_descriptions()) if hasattr(options, 'server_descriptions') else "unknown",
            "status": "connected" if MongoHealthCheck.is_connected else "disconnected",
            "health_status": "healthy" if MongoHealthCheck.failure_count == 0 else f"degraded ({MongoHealthCheck.failure_count} failures)",
        }
        
        logger.info(f"[DB_POOL] Pool stats: {stats}")
        return stats
        
    except Exception as e:
        logger.warning(f"[DB_POOL] Could not retrieve pool stats: {type(e).__name__}")
        return {"status": "unknown"}
