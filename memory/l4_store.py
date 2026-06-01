"""
ASTA Memory Layer - L4 Cold Store (MongoDB)
──────────────────────────────────────────

This is the L4 cold storage layer using MongoDB (motor async driver).
Handles full session documents, permanent memory, entities, and content logs.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, TEXT
from backend.app.config import settings
from memory.schema import SessionMetadata, Entity

logger = logging.getLogger(__name__)

class L4Store:
    """
    L4 cold storage layer using MongoDB.
    
    Collections used:
    - "sessions"           → full session documents + summaries
    - "permanent_memory"   → things Karthik explicitly said "remember this"
    - "entities"           → known entity registry (deduplicated)
    - "content_logs"       → post-creation audit trail
    """
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        
    async def connect(self) -> None:
        """Connect to MongoDB and create indexes."""
        try:
            self.client = AsyncIOMotorClient(settings.MONGO_URI)
            self.db = self.client[settings.DB_NAME]
            
            # Ping to verify connection
            await self.client.admin.command('ping')
            
            # Create indexes
            await self._create_indexes()
            
            logger.info("L4 MongoDB connected")
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    async def _create_indexes(self) -> None:
        """Create required indexes on startup."""
        try:
            # Sessions collection indexes
            sessions_indexes = [
                IndexModel([("session_id", ASCENDING)], unique=True, name="session_id_unique_v2"),
                IndexModel([("workflow_type", ASCENDING)]),
                IndexModel([("entities.name", ASCENDING)]),
                IndexModel([("end_time", ASCENDING)]),
                IndexModel([("raw_transcript_expires_at", ASCENDING)], expireAfterSeconds=0)  # TTL index
            ]
            
            # Drop existing conflicting index if it exists
            try:
                await self.db.sessions.drop_index("session_id_unique")
            except Exception:
                pass  # Index might not exist
                
            await self.db.sessions.create_indexes(sessions_indexes)
            
            # Permanent memory indexes
            perm_indexes = [
                IndexModel([("tags", ASCENDING)]),  # Array index
                IndexModel([("memory_id", ASCENDING)], unique=True)
            ]
            await self.db.permanent_memory.create_indexes(perm_indexes)
            
            # Entities indexes
            entity_indexes = [
                IndexModel([("name", ASCENDING), ("entity_type", ASCENDING)], unique=True)
            ]
            await self.db.entities.create_indexes(entity_indexes)
            
            logger.info("L4 MongoDB indexes created")
            
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            # Don't raise - indexes might already exist
    
    async def save_session(self, metadata: SessionMetadata, raw_transcript: List[Dict]) -> bool:
        """
        Save a complete session document.
        
        Args:
            metadata: SessionMetadata object with session info
            raw_transcript: List of message dicts from the session
            
        Returns:
            True on success, False on failure
        """
        try:
            # Convert entities to dict format for storage
            entities_dict = [
                {
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "description": entity.description,
                    "confidence": entity.confidence
                }
                for entity in metadata.entities
            ]
            
            # Ensure summary is a string, not a list
            summary_str = metadata.summary
            if isinstance(summary_str, list):
                summary_str = " ".join(str(item) for item in summary_str)
            elif not isinstance(summary_str, str):
                summary_str = str(summary_str)
            
            document = {
                "session_id": metadata.session_id,
                "workflow_type": metadata.workflow_type,
                "start_time": metadata.start_time,
                "end_time": metadata.end_time,
                "summary": summary_str,  # Guaranteed to be string
                "entities": entities_dict,
                "topics": metadata.topics,
                "embedding_id": metadata.embedding_id,
                "notion_page_id": metadata.notion_page_id,
                "raw_transcript": raw_transcript,
                "raw_transcript_expires_at": datetime.utcnow() + timedelta(days=settings.SESSION_TRANSCRIPT_TTL_DAYS)
            }
            
            # Upsert on session_id
            await self.db.sessions.replace_one(
                {"session_id": metadata.session_id},
                document,
                upsert=True
            )
            
            logger.info(f"Session {metadata.session_id} saved to L4")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session {metadata.session_id}: {e}")
            return False
    
    async def get_sessions_by_ids(self, session_ids: List[str]) -> List[Dict]:
        """
        Fetch sessions by session_id list.
        Returns only metadata, excludes raw_transcript for privacy.
        """
        try:
            cursor = self.db.sessions.find(
                {"session_id": {"$in": session_ids}},
                {
                    "session_id": 1,
                    "workflow_type": 1,
                    "summary": 1,
                    "entities": 1,
                    "topics": 1,
                    "end_time": 1,
                    "start_time": 1,
                    "notion_page_id": 1,
                    "_id": 0
                }
            )
            
            sessions = await cursor.to_list(length=None)
            logger.info(f"Retrieved {len(sessions)} sessions from L4")
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get sessions by IDs: {e}")
            return []
    
    async def save_permanent_memory(self, content: str, tags: List[str]) -> Dict:
        """
        Save to permanent_memory collection.
        
        Returns:
            The saved document dict
        """
        try:
            memory_id = str(uuid4())
            document = {
                "memory_id": memory_id,
                "content": content,
                "tags": tags,
                "date_stored": datetime.utcnow().isoformat(),
                "recalled_count": 0
            }
            
            await self.db.permanent_memory.insert_one(document)
            
            # Remove MongoDB _id for return
            document.pop("_id", None)
            
            logger.info(f"Permanent memory saved: {memory_id}")
            return document
            
        except Exception as e:
            logger.error(f"Failed to save permanent memory: {e}")
            return {}
    
    async def get_permanent_memories_by_tags(self, tags: List[str]) -> List[Dict]:
        """
        Query permanent_memory where tags array intersects with input tags.
        """
        try:
            cursor = self.db.permanent_memory.find(
                {"tags": {"$in": tags}},
                {"_id": 0}  # Exclude MongoDB _id
            )
            
            memories = await cursor.to_list(length=None)
            logger.info(f"Retrieved {len(memories)} permanent memories")
            return memories
            
        except Exception as e:
            logger.error(f"Failed to get permanent memories: {e}")
            return []
    
    async def increment_recalled_count(self, memory_id: str) -> None:
        """Increment recalled_count by 1 for a permanent memory."""
        try:
            await self.db.permanent_memory.update_one(
                {"memory_id": memory_id},
                {"$inc": {"recalled_count": 1}}
            )
            
        except Exception as e:
            logger.error(f"Failed to increment recall count for {memory_id}: {e}")
    
    async def save_entity(self, entity: Entity) -> None:
        """
        Upsert entity into entities collection by name + entity_type.
        Update description if provided.
        """
        try:
            document = {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "description": entity.description,
                "confidence": entity.confidence,
                "last_seen": datetime.utcnow().isoformat()
            }
            
            await self.db.entities.replace_one(
                {"name": entity.name, "entity_type": entity.entity_type},
                document,
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"Failed to save entity {entity.name}: {e}")
    
    async def get_all_entities(self) -> List[Dict]:
        """Return all known entities (used for Neo4j sync on startup)."""
        try:
            cursor = self.db.entities.find({}, {"_id": 0})
            entities = await cursor.to_list(length=None)
            return entities
            
        except Exception as e:
            logger.error(f"Failed to get all entities: {e}")
            return []
    
    async def save_content_log(self, platform: str, topic: str, summary: str) -> None:
        """Append to content_logs collection."""
        try:
            document = {
                "platform": platform,
                "topic": topic,
                "summary": summary,
                "date": datetime.utcnow().isoformat()
            }
            
            await self.db.content_logs.insert_one(document)
            
        except Exception as e:
            logger.error(f"Failed to save content log: {e}")
    
    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()

# Export singleton
l4_store = L4Store()