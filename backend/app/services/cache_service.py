"""
Cache Service - Simple caching layer
Wraps Redis or provides in-memory fallback
"""

import logging
from typing import Optional, Any, Dict
import json

logger = logging.getLogger(__name__)


class CacheService:
    """
    Simple cache service with Redis backend or in-memory fallback
    Supports both instance and class-level methods for backward compatibility
    """
    
    _instance = None
    
    def __init__(self):
        self._redis = None
        self._memory_cache: Dict[str, Any] = {}
        self._initialized = False
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = CacheService()
            await cls._instance.initialize()
        return cls._instance
    
    @classmethod
    async def get_json(cls, key: str) -> Optional[Dict]:
        """Class method to get JSON value"""
        instance = await cls.get_instance()
        return await instance.get(key)
    
    @classmethod
    async def set_json(cls, key: str, value: Dict, ttl: int = 3600, ttl_seconds: int = None):
        """Class method to set JSON value (supports both ttl and ttl_seconds for backward compatibility)"""
        instance = await cls.get_instance()
        actual_ttl = ttl_seconds if ttl_seconds is not None else ttl
        await instance.set(key, value, actual_ttl)

    @classmethod
    async def set_session_cache(cls, session_id: str, payload: Dict, ttl_seconds: int = 3600):
        """Class method to set session cache with key prefix session_cache:"""
        await cls.set_json(f"session_cache:{session_id}", payload, ttl=ttl_seconds)

    @classmethod
    async def get_session_cache(cls, session_id: str) -> Optional[Dict]:
        """Class method to get session cache with key prefix session_cache:"""
        return await cls.get_json(f"session_cache:{session_id}")

    @classmethod
    async def delete_session_cache(cls, session_id: str):
        """Class method to delete session cache"""
        instance = await cls.get_instance()
        await instance.delete(f"session:{session_id}")
        await instance.delete(f"session_cache:{session_id}")
    
    async def initialize(self):
        """Initialize cache connection"""
        if self._initialized:
            return
        
        try:
            from backend.app.core.registry import registry
            self._redis = registry.get("redis")
            
            if self._redis:
                # Test connection
                await self._redis.ping()
                logger.info("CacheService: Using Redis backend")
            else:
                logger.warning("CacheService: Redis not available, using in-memory cache")
            
            self._initialized = True
        except Exception as e:
            logger.warning(f"CacheService: Failed to connect to Redis: {e}, using in-memory cache")
            self._redis = None
            self._initialized = True
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if self._redis:
                value = await self._redis.get(key)
                if value:
                    try:
                        return json.loads(value)
                    except:
                        return value
                return None
            else:
                return self._memory_cache.get(key)
        except Exception as e:
            logger.error(f"CacheService.get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL in seconds"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if self._redis:
                if isinstance(value, (dict, list)):
                    class DateTimeEncoder(json.JSONEncoder):
                        def default(self, obj):
                            from datetime import datetime, date
                            if isinstance(obj, (datetime, date)):
                                return obj.isoformat()
                            return super().default(obj)
                    value = json.dumps(value, cls=DateTimeEncoder)
                await self._redis.setex(key, ttl, value)
            else:
                self._memory_cache[key] = value
        except Exception as e:
            logger.error(f"CacheService.set error: {e}")
    
    async def delete(self, key: str):
        """Delete key from cache"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if self._redis:
                await self._redis.delete(key)
            else:
                self._memory_cache.pop(key, None)
        except Exception as e:
            logger.error(f"CacheService.delete error: {e}")
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if self._redis:
                return await self._redis.exists(key) > 0
            else:
                return key in self._memory_cache
        except Exception as e:
            logger.error(f"CacheService.exists error: {e}")
            return False
    
    async def clear(self):
        """Clear all cache (use with caution)"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if self._redis:
                # Don't clear entire Redis, just log warning
                logger.warning("CacheService.clear: Not clearing Redis (shared resource)")
            else:
                self._memory_cache.clear()
        except Exception as e:
            logger.error(f"CacheService.clear error: {e}")
    
    async def get_many(self, keys: list) -> Dict[str, Any]:
        """Get multiple values at once"""
        if not self._initialized:
            await self.initialize()
        
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    async def set_many(self, items: Dict[str, Any], ttl: int = 3600):
        """Set multiple values at once"""
        if not self._initialized:
            await self.initialize()
        
        for key, value in items.items():
            await self.set(key, value, ttl)
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if self._redis:
                return await self._redis.incr(key, amount)
            else:
                current = self._memory_cache.get(key, 0)
                new_value = current + amount
                self._memory_cache[key] = new_value
                return new_value
        except Exception as e:
            logger.error(f"CacheService.increment error: {e}")
            return 0
    
    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a counter"""
        return await self.increment(key, -amount)


# Global singleton instance
cache_service = CacheService()
