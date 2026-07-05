"""
L1 Cache Service - Compatibility Layer
Bridges old l1_manager calls to new memory layer
"""

import logging
from typing import Optional, Dict, Any
import sys
import os

# Add memory layer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from memory.l1_cache import L1Cache

logger = logging.getLogger(__name__)


class SessionCache:
    """Session-specific cache wrapper"""
    
    def __init__(self, session_id: str, l1_cache: L1Cache):
        self.session_id = session_id
        self.l1_cache = l1_cache
    
    async def set_speculative_data(self, key: str, value: Any = None, ttl: int = 300, data: Any = None, trigger_query: str = None):
        """Store speculative/prefetch data"""
        if value is None:
            if data is not None or trigger_query is not None:
                value = {
                    "data": data,
                    "trigger_query": trigger_query
                }
        cache_key = f"speculative:{self.session_id}:{key}"
        await self.l1_cache.set(cache_key, value, ttl=ttl)
    
    async def get_speculative_data(self, key: str) -> Optional[Any]:
        """Retrieve speculative data"""
        cache_key = f"speculative:{self.session_id}:{key}"
        return await self.l1_cache.get(cache_key)
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Store session data"""
        cache_key = f"session:{self.session_id}:{key}"
        await self.l1_cache.set(cache_key, value, ttl=ttl)
    
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve session data"""
        cache_key = f"session:{self.session_id}:{key}"
        return await self.l1_cache.get(cache_key)
    
    def get_llm_history(self) -> list:
        """
        Get LLM conversation history for this session.
        Returns empty list for now - history is managed by SessionManager.
        """
        # TODO: Integrate with SessionManager for proper history retrieval
        return []
    
    async def append_turn(self, user_msg: str, assistant_msg: str):
        """
        Append a conversation turn to session history.
        For now, this is a no-op as history is managed by SessionManager.
        """
        # TODO: Integrate with SessionManager for proper history storage
        pass


class L1Manager:
    """
    L1 Cache Manager - Compatibility layer for legacy code
    Wraps the new memory layer's L1Cache
    """
    
    def __init__(self):
        self._l1_cache: Optional[L1Cache] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the L1 cache connection"""
        if self._initialized:
            return
        
        try:
            from backend.app.config import settings
            redis_url = settings.REDIS_URL or "redis://localhost:6379/0"
            
            self._l1_cache = L1Cache(redis_url=redis_url)
            await self._l1_cache.connect()
            self._initialized = True
            logger.info("L1 Cache Manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize L1 Cache Manager: {e}")
            # Create a mock cache for graceful degradation
            self._l1_cache = None
    
    def get_session(self, session_id: str) -> SessionCache:
        """Get a session-specific cache wrapper"""
        if not self._initialized:
            # Return a no-op cache if not initialized
            return SessionCache(session_id, MockL1Cache())
        
        return SessionCache(session_id, self._l1_cache or MockL1Cache())
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set a global cache value"""
        if self._l1_cache:
            await self._l1_cache.set(key, value, ttl=ttl)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a global cache value"""
        if self._l1_cache:
            return await self._l1_cache.get(key)
        return None
    
    async def delete(self, key: str):
        """Delete a cache key"""
        if self._l1_cache:
            await self._l1_cache.delete(key)
    
    async def close(self):
        """Close the cache connection"""
        if self._l1_cache:
            await self._l1_cache.disconnect()
            self._initialized = False


class MockL1Cache:
    """Mock cache for graceful degradation when Redis is unavailable"""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
    
    async def connect(self):
        pass
    
    async def disconnect(self):
        pass
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        self._data[key] = value
    
    async def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)
    
    async def delete(self, key: str):
        self._data.pop(key, None)


# Global singleton instance
l1_manager = L1Manager()


# Auto-initialize on import (for backward compatibility)
async def _auto_init():
    await l1_manager.initialize()


# Note: Actual initialization should happen in app startup
# This is just for backward compatibility
