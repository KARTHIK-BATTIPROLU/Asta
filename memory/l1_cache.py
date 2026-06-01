"""
ASTA Memory Layer - L1 Hot Cache (Redis)
───────────────────────────────────────

This is the L1 hot cache using Redis async client.
Handles active sessions, entity context cache, and retrieved context cache.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import redis.asyncio as redis
from backend.app.config import settings
from memory.schema import CachedContext, ActiveSession

logger = logging.getLogger(__name__)

class L1Cache:
    """
    L1 hot cache using Redis async client.
    
    Manages:
    - Active session tracking
    - Entity context cache (pre-fetched)
    - Retrieved context cache (per session)
    """
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        
    async def connect(self) -> None:
        """Connect to Redis and verify connection."""
        try:
            self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.client.ping()
            logger.info("L1 Redis connected")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    # ── Active Session Tracking ──────────────────────────────────────────────
    
    async def start_session(self, session_id: str, workflow_type: str) -> None:
        """Start tracking an active session."""
        try:
            session = ActiveSession(
                session_id=session_id,
                workflow_type=workflow_type,
                start_time=datetime.utcnow().isoformat()
            )
            
            key = f"active_session:{session_id}"
            await self.client.setex(
                key, 
                settings.REDIS_TTL_HOT, 
                json.dumps(session.__dict__)
            )
            
            logger.info(f"Started tracking session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to start session {session_id}: {e}")
    
    async def get_active_session(self, session_id: str) -> Optional[Dict]:
        """Get active session data."""
        try:
            key = f"active_session:{session_id}"
            data = await self.client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get active session {session_id}: {e}")
            return None
    
    async def add_entity_to_session(self, session_id: str, entity_name: str) -> None:
        """Add an entity to the session's entities_seen list."""
        try:
            key = f"active_session:{session_id}"
            data = await self.client.get(key)
            
            if data:
                session = json.loads(data)
                entities_seen = session.get("entities_seen", [])
                
                if entity_name not in entities_seen:
                    entities_seen.append(entity_name)
                    session["entities_seen"] = entities_seen
                    
                    # Preserve TTL
                    ttl = await self.client.ttl(key)
                    await self.client.setex(
                        key, 
                        max(ttl, 60),  # At least 60 seconds
                        json.dumps(session)
                    )
                    
                    logger.debug(f"Added entity {entity_name} to session {session_id}")
                    
        except Exception as e:
            logger.error(f"Failed to add entity to session {session_id}: {e}")
    
    async def end_session(self, session_id: str) -> None:
        """Remove active session tracking."""
        try:
            key = f"active_session:{session_id}"
            await self.client.delete(key)
            
        except Exception as e:
            logger.error(f"Failed to end session {session_id}: {e}")
    
    # ── Entity Context Cache ─────────────────────────────────────────────────
    
    async def cache_entity_context(self, entity_name: str, sessions: List[Dict]) -> None:
        """Store pre-fetched context for an entity."""
        try:
            key = f"entity_ctx:{entity_name.lower().replace(' ', '_')}"
            
            payload = {
                "entity_name": entity_name,
                "related_sessions": sessions,
                "last_updated": datetime.utcnow().isoformat(),
                "hit_count": 0
            }
            
            await self.client.setex(
                key, 
                settings.REDIS_TTL_ENTITY, 
                json.dumps(payload)
            )
            
            logger.info(f"Cached context for entity: {entity_name}")
            
        except Exception as e:
            logger.error(f"Failed to cache entity context for {entity_name}: {e}")
    
    async def get_entity_context(self, entity_name: str) -> Optional[Dict]:
        """Get cached context for an entity and increment hit count."""
        try:
            key = f"entity_ctx:{entity_name.lower().replace(' ', '_')}"
            data = await self.client.get(key)
            
            if data:
                payload = json.loads(data)
                
                # Increment hit count
                payload["hit_count"] = payload.get("hit_count", 0) + 1
                
                # Update cache with new hit count, preserve TTL
                ttl = await self.client.ttl(key)
                await self.client.setex(
                    key, 
                    max(ttl, 60), 
                    json.dumps(payload)
                )
                
                logger.debug(f"Retrieved entity context for {entity_name} (hits: {payload['hit_count']})")
                return payload
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get entity context for {entity_name}: {e}")
            return None
    
    async def invalidate_entity_context(self, entity_name: str) -> None:
        """Remove cached context for an entity."""
        try:
            key = f"entity_ctx:{entity_name.lower().replace(' ', '_')}"
            await self.client.delete(key)
            
        except Exception as e:
            logger.error(f"Failed to invalidate entity context for {entity_name}: {e}")
    
    # ── Retrieved Context Cache (per session) ────────────────────────────────
    
    async def cache_retrieved_context(self, session_id: str, context: List[Dict]) -> None:
        """Cache the result of the full retrieval pipeline for this session."""
        try:
            key = f"retrieved_ctx:{session_id}"
            await self.client.setex(
                key, 
                settings.REDIS_TTL_HOT, 
                json.dumps(context)
            )
            
            logger.info(f"Cached retrieved context for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to cache retrieved context for {session_id}: {e}")
    
    async def get_retrieved_context(self, session_id: str) -> Optional[List[Dict]]:
        """Get cached retrieved context for a session."""
        try:
            key = f"retrieved_ctx:{session_id}"
            data = await self.client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get retrieved context for {session_id}: {e}")
            return None
    
    # ── Utility ──────────────────────────────────────────────────────────────
    
    async def flush_session_keys(self, session_id: str) -> None:
        """Clean up all keys for a completed session."""
        try:
            keys_to_delete = [
                f"active_session:{session_id}",
                f"retrieved_ctx:{session_id}"
            ]
            
            await self.client.delete(*keys_to_delete)
            logger.info(f"Flushed session keys for {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to flush session keys for {session_id}: {e}")
    
    async def health_check(self) -> bool:
        """Check if Redis is responsive."""
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.aclose()

# Export singleton
l1_cache = L1Cache()