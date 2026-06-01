"""
Saga Retry Worker for ASTA
Background task that retries failed Pinecone and Neo4j writes
"""
import logging
import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, Any

from memory.memory_saga import memory_saga

logger = logging.getLogger("SagaRetryWorker")


class SagaRetryWorker:
    """
    Background worker that polls MongoDB for failed saga steps.
    Retries with exponential backoff: 30s → 60s → 120s
    Marks as dead_letter after 3 failures.
    """
    
    def __init__(self):
        self.mongo_client = None
        self.db = None
        self._initialized = False
        
        self.running = False
        self.task = None
        
        # Retry configuration
        self.retry_delays = [30, 60, 120]  # seconds
        self.max_retries = 3
        
        logger.info("SagaRetryWorker initialized")
    
    def _ensure_initialized(self):
        """Lazy initialization"""
        if self._initialized:
            return
        
        mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGODB_URI or MONGO_URI environment variable required")
        
        self.mongo_client = AsyncIOMotorClient(mongo_uri)
        self.db = self.mongo_client.get_database("asta_memory")
        self._initialized = True
    
    async def start(self):
        """Start background retry worker"""
        if self.running:
            logger.warning("SagaRetryWorker already running")
            return
        
        self._ensure_initialized()
        
        self.running = True
        self.task = asyncio.create_task(self._retry_loop())
        logger.info("SagaRetryWorker started")
    
    async def stop(self):
        """Stop background retry worker"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("SagaRetryWorker stopped")
    
    async def _retry_loop(self):
        """Main retry loop - runs every 30 seconds"""
        while self.running:
            try:
                await self._process_retries()
            except Exception as e:
                logger.error(f"Retry loop error: {e}")
            
            # Wait 30 seconds before next poll
            await asyncio.sleep(30)
    
    async def _process_retries(self):
        """Process all pending retries"""
        collection = self.db["sessions"]
        
        # Find sessions with pending embedding or neo4j writes
        query = {
            "$or": [
                {"embedding_status": "pending"},
                {"neo4j_status": "pending"}
            ]
        }
        
        cursor = collection.find(query).limit(50)
        sessions = await cursor.to_list(length=50)
        
        if not sessions:
            return
        
        logger.info(f"Found {len(sessions)} sessions with pending writes")
        
        for session_doc in sessions:
            session_id = session_doc["session_id"]
            
            # Check retry count
            retry_count = session_doc.get("retry_count", 0)
            
            if retry_count >= self.max_retries:
                # Mark as dead letter
                await self._mark_dead_letter(session_id, session_doc)
                continue
            
            # Check if enough time has passed for retry
            last_retry = session_doc.get("last_retry_at")
            if last_retry:
                # Calculate required delay based on retry count
                required_delay = self.retry_delays[min(retry_count, len(self.retry_delays) - 1)]
                elapsed = (datetime.now(timezone.utc) - last_retry).total_seconds()
                
                if elapsed < required_delay:
                    continue  # Not ready for retry yet
            
            # Attempt retry
            await self._retry_session(session_id, session_doc, retry_count)
    
    async def _retry_session(
        self,
        session_id: str,
        session_doc: Dict[str, Any],
        retry_count: int
    ):
        """Retry failed steps for a session"""
        logger.info(f"Retrying session {session_id} (attempt {retry_count + 1}/{self.max_retries})")
        
        collection = self.db["sessions"]
        
        # Update retry metadata
        await collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "last_retry_at": datetime.now(timezone.utc),
                    "retry_count": retry_count + 1
                }
            }
        )
        
        # Retry Pinecone if pending
        if session_doc.get("embedding_status") == "pending":
            try:
                success = await memory_saga._write_pinecone(
                    session_id=session_id,
                    summary=session_doc["summary"],
                    topics=session_doc.get("topics", []),
                    timestamp=session_doc["timestamp"]
                )
                
                if success:
                    await collection.update_one(
                        {"session_id": session_id},
                        {"$set": {"embedding_status": "complete"}}
                    )
                    logger.info(f"Pinecone retry successful for {session_id}")
                else:
                    logger.warning(f"Pinecone retry failed for {session_id}")
                    
            except Exception as e:
                logger.error(f"Pinecone retry error for {session_id}: {e}")
        
        # Retry Neo4j if pending
        if session_doc.get("neo4j_status") == "pending":
            try:
                # Reconstruct session data for Neo4j write
                from memory.memory_saga import SessionData
                
                session_data = SessionData(
                    session_id=session_id,
                    user_id=session_doc.get("user_id", "karthik"),
                    timestamp=session_doc["timestamp"],
                    ended_at=session_doc["ended_at"],
                    duration_seconds=session_doc["duration_seconds"],
                    raw_messages=session_doc.get("raw_messages", []),
                    message_count=session_doc["message_count"],
                    tool_calls=session_doc.get("tool_calls", [])
                )
                
                # Re-extract entities
                entities = await memory_saga._extract_entities(
                    session_data,
                    session_doc["summary"]
                )
                
                # Retry Neo4j write
                success = await memory_saga._write_neo4j(
                    session_data=session_data,
                    summary=session_doc["summary"],
                    topics=session_doc.get("topics", []),
                    entities=entities
                )
                
                if success:
                    await collection.update_one(
                        {"session_id": session_id},
                        {"$set": {"neo4j_status": "complete"}}
                    )
                    logger.info(f"Neo4j retry successful for {session_id}")
                else:
                    logger.warning(f"Neo4j retry failed for {session_id}")
                    
            except Exception as e:
                logger.error(f"Neo4j retry error for {session_id}: {e}")
    
    async def _mark_dead_letter(
        self,
        session_id: str,
        session_doc: Dict[str, Any]
    ):
        """Mark session as dead letter after max retries"""
        logger.critical(
            f"DEAD LETTER: Session {session_id} failed after {self.max_retries} retries. "
            f"embedding_status={session_doc.get('embedding_status')}, "
            f"neo4j_status={session_doc.get('neo4j_status')}"
        )
        
        collection = self.db["sessions"]
        
        # Update status
        updates = {}
        if session_doc.get("embedding_status") == "pending":
            updates["embedding_status"] = "dead_letter"
        if session_doc.get("neo4j_status") == "pending":
            updates["neo4j_status"] = "dead_letter"
        
        updates["dead_letter_at"] = datetime.now(timezone.utc)
        
        await collection.update_one(
            {"session_id": session_id},
            {"$set": updates}
        )
        
        # TODO: Send critical alert (email, Slack, etc.)
        # For now, just log critically
        logger.critical(f"Session {session_id} marked as DEAD LETTER - manual intervention required")


# Global instance
saga_retry_worker = SagaRetryWorker()
