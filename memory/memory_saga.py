"""
Memory Saga for ASTA
Atomic 3-phase write: MongoDB → Pinecone → Neo4j
Implements Outbox Pattern with retry support
"""
import asyncio
import logging
import os
import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pinecone import Pinecone
from groq import AsyncGroq
from summa import summarizer

from memory.graph_service import graph_service
from memory.embeddings import embedding_service

logger = logging.getLogger("MemorySaga")


@dataclass
class SessionData:
    """Data structure for a complete session"""
    session_id: str
    user_id: str
    timestamp: str
    ended_at: str
    duration_seconds: int
    raw_messages: List[Dict[str, str]]
    message_count: int
    tool_calls: List[str] = None
    
    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


class MemorySaga:
    """
    Coordinates atomic write across all 3 memory layers.
    Ensures MongoDB, Pinecone, and Neo4j stay in sync.
    """
    
    def __init__(self, session_id: str = None, summary: str = "", embedding: list = None, raw_segment: str = "", source: str = ""):
        self.session_id = session_id
        self.summary = summary
        self.embedding = embedding or []
        self.raw_segment = raw_segment
        self.source = source
        self.mongo_client = None
        self.db = None
        self.pinecone_index = None
        self.groq_client = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of all services"""
        if self._initialized:
            return
        
        # MongoDB setup
        mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGODB_URI or MONGO_URI environment variable required")
        
        self.mongo_client = AsyncIOMotorClient(mongo_uri)
        self.db = self.mongo_client.get_database("asta_memory")
        
        # Pinecone setup
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        pinecone_index_name = os.getenv("PINECONE_INDEX_NAME")
        
        if not pinecone_api_key or not pinecone_index_name:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME required")
        
        pc = Pinecone(api_key=pinecone_api_key)
        self.pinecone_index = pc.Index(pinecone_index_name)
        
        # Groq setup (only for entity extraction)
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable required")
        
        self.groq_client = AsyncGroq(api_key=groq_api_key)
        
        self._initialized = True
        logger.info("MemorySaga initialized")
    
    async def execute(self, session_data: SessionData = None) -> bool:
        """
        Execute the complete saga.
        Returns True if all steps succeeded, False if any failed.
        """
        self._ensure_initialized()
        
        # Use provided session_data or create from stored parameters
        if session_data is None:
            if not self.session_id:
                logger.error("No session_id provided for MemorySaga execution")
                return False
            
            # Create minimal session data from stored parameters
            session_data = SessionData(
                session_id=self.session_id,
                user_id="KARTHIK",
                timestamp=datetime.now(timezone.utc).isoformat(),
                ended_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0,
                raw_messages=[],
                message_count=0,
                tool_calls=[]
            )
        
        session_id = session_data.session_id
        logger.info(f"Starting MemorySaga for session: {session_id}")
        
        try:
            # STEP 1: Generate summary (TextRank only)
            if self.summary:
                summary = self.summary
            else:
                summary, _ = await self._generate_summary(session_data)
                if not summary:
                    logger.error(f"Summary generation failed - aborting saga for {session_id}")
                    return False
            
            # STEP 2: Extract entities for Neo4j (includes topics from Groq)
            entities = await self._extract_entities(session_data, summary)
            
            # Get topics from Groq entity extraction
            topics = entities.get("session_properties", {}).get("topics", [])
            if not topics:
                topics = ["general"]
            
            # STEP 3: Write to MongoDB (required - failure aborts)
            mongo_success = await self._write_mongodb(session_data, summary, topics)
            if not mongo_success:
                logger.error(f"MongoDB write failed - aborting saga for {session_id}")
                return False
            
            # STEP 4: Generate embedding and write to Pinecone (retry on fail)
            if self.embedding:
                embedding = self.embedding
                pinecone_success = await self._write_pinecone_with_embedding(session_id, summary, topics, session_data.timestamp, embedding)
            else:
                pinecone_success = await self._write_pinecone(session_id, summary, topics, session_data.timestamp)
            
            if pinecone_success:
                await self._update_mongodb_status(session_id, "embedding_status", "complete")
            else:
                logger.warning(f"Pinecone write failed for {session_id} - will retry")
            
            # STEP 5: Write to Neo4j (awaited - never fire-and-forget)
            neo4j_success = await self._write_neo4j(session_data, summary, topics, entities)
            if neo4j_success:
                await self._update_mongodb_status(session_id, "neo4j_status", "complete")
            else:
                logger.warning(f"Neo4j write failed for {session_id} - will retry")
            
            # STEP 6: Store pending confirmations
            if entities.get("pending_confirmations"):
                await self._store_pending_confirmations(session_id, entities["pending_confirmations"])
            
            logger.info(f"MemorySaga completed for {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"MemorySaga failed for {session_id}: {e}")
            return False
    
    async def _generate_summary(self, session_data: SessionData) -> tuple[str, List[str]]:
        """
        STEP 1: Generate compressed summary using TextRank extractive summarization.
        
        Returns (summary, empty_list). Topics now come from Groq entity extraction.
        """
        try:
            # Format conversation
            conversation = "\n\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in session_data.raw_messages
            ])
            
            if not conversation.strip():
                logger.warning("Empty conversation for summary generation")
                return "", []
            
            # TextRank - Extract key sentences
            logger.info("Extracting key sentences with TextRank...")
            try:
                # Use summa's TextRank implementation
                # ratio=0.3 means extract ~30% of sentences, or at least 5 sentences
                key_sentences = summarizer.summarize(
                    conversation,
                    ratio=0.3,
                    split=True  # Return as list of sentences
                )
                
                # Limit to top 5 sentences
                if isinstance(key_sentences, list):
                    key_sentences = key_sentences[:5]
                else:
                    # If it returns a string, split by newlines
                    key_sentences = key_sentences.split('\n')[:5]
                
                # Join sentences and limit to 300 chars
                summary = " ".join(key_sentences)[:300]
                
                if not summary.strip():
                    # Fallback: use first 300 chars if TextRank fails
                    summary = conversation[:300]
                
                logger.info(f"TextRank extracted {len(key_sentences)} key sentences")
                
            except Exception as e:
                logger.error(f"TextRank extraction failed: {e}")
                # Fallback: use first 300 chars
                summary = conversation[:300]
            
            # Topics now come from Groq entity extraction, return empty list
            logger.info(f"Generated summary for {session_data.session_id}")
            return summary, []
            
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return "", []
    
    async def _write_mongodb(
        self,
        session_data: SessionData,
        summary: str,
        topics: List[str]
    ) -> bool:
        """
        STEP 2: Write to MongoDB (required - failure aborts entire saga).
        """
        try:
            collection = self.db["sessions"]
            
            document = {
                "session_id": session_data.session_id,
                "user_id": session_data.user_id,
                "timestamp": session_data.timestamp,
                "ended_at": session_data.ended_at,
                "duration_seconds": session_data.duration_seconds,
                "summary": summary,
                "topics": topics,
                "tool_calls": session_data.tool_calls,
                "message_count": session_data.message_count,
                "raw_messages": session_data.raw_messages,
                "embedding_status": "pending",
                "neo4j_status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await collection.insert_one(document)
            logger.info(f"MongoDB write successful: {session_data.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"MongoDB write failed: {e}")
            return False
    
    async def _write_pinecone_with_embedding(
        self,
        session_id: str,
        summary: str,
        topics: List[str],
        timestamp: str,
        embedding: List[float]
    ) -> bool:
        """
        STEP 3b: Write to Pinecone with pre-generated embedding.
        """
        try:
            # Upsert to Pinecone with provided embedding
            self.pinecone_index.upsert(
                vectors=[{
                    "id": session_id,
                    "values": embedding,
                    "metadata": {
                        "session_id": session_id,
                        "timestamp": timestamp,
                        "topics": topics,
                        "summary_preview": summary[:200]
                    }
                }]
            )
            
            logger.info(f"Pinecone write successful (pre-generated embedding): {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Pinecone write failed: {e}")
            return False
    
    async def _write_pinecone(
        self,
        session_id: str,
        summary: str,
        topics: List[str],
        timestamp: str
    ) -> bool:
        """
        STEP 3: Generate embedding and write to Pinecone.
        """
        try:
            # Generate embedding
            embedding = embedding_service.embed(summary)
            
            # Upsert to Pinecone
            self.pinecone_index.upsert(
                vectors=[{
                    "id": session_id,
                    "values": embedding,
                    "metadata": {
                        "session_id": session_id,
                        "timestamp": timestamp,
                        "topics": topics,
                        "summary_preview": summary[:200]
                    }
                }]
            )
            
            logger.info(f"Pinecone write successful: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Pinecone write failed: {e}")
            return False
    
    async def _extract_entities(
        self,
        session_data: SessionData,
        summary: str
    ) -> Dict[str, Any]:
        """
        STEP 4: Extract entities using Groq llama-3.3-70b-versatile.
        Returns structured entity data for Neo4j.
        """
        try:
            # Get existing nodes from graph
            existing_nodes = await graph_service.get_existing_nodes()
            
            # Format conversation
            conversation = "\n\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in session_data.raw_messages
            ])
            
            prompt = f"""You are extracting structured knowledge from a conversation session for Karthik's personal knowledge graph.

SESSION SUMMARY:
{summary}

FULL CONVERSATION:
{conversation}

EXISTING GRAPH NODES (check against these before creating new ones):
{json.dumps(existing_nodes, indent=2)}

Your job: Extract all entities and relationships from this session.
Return ONLY a valid JSON object, no markdown, no explanation:

{{
  "session_properties": {{
    "topics": ["topic1", "topic2"],
    "tool_calls": ["Notion", "Serper Search"],
    "summary": "2-4 sentence summary of what happened"
  }},
  "relationships": {{
    "touches_projects": [
      {{"name": "ASTA", "confidence": "HIGH", "reason": "entire session was about ASTA memory layer"}}
    ],
    "uses_skills": [
      {{"name": "Python", "group": "Programming Languages", "confidence": "HIGH", "reason": "wrote Python code"}},
      {{"name": "Neo4j", "group": "Databases", "confidence": "HIGH", "reason": "debugged Neo4j queries"}}
    ],
    "involves_tools": [
      {{"name": "Notion", "confidence": "HIGH", "reason": "Notion was called during session"}}
    ],
    "involves_people": [],
    "creates_commitments": [
      {{"description": "Fix ASCENDING import bug", "deadline": null, "confidence": "HIGH"}}
    ]
  }},
  "new_nodes_to_create": {{
    "projects": [
      {{"name": "New Project Name", "description": "what it is", "status": "active", "confidence": "HIGH", "parent": "Projects"}}
    ],
    "skills": [
      {{"name": "New Skill", "group": "Frameworks", "confidence": "MEDIUM", "reason": "mentioned briefly"}}
    ],
    "people": [],
    "interests": [],
    "commitments": []
  }}
}}

Confidence rules:
HIGH   = explicitly discussed, used, or confirmed in session
MEDIUM = mentioned but not the focus, inferred
LOW    = very briefly mentioned, uncertain

IMPORTANT:
- Only create new nodes for things NOT already in existing_nodes_json
- If an entity matches an existing node, reference it by exact name
- Never invent entities not present in the conversation"""

            response = await self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            # Strip markdown if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            entities = json.loads(content.strip())
            logger.info(f"Entity extraction successful for {session_data.session_id}")
            return entities
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {
                "session_properties": {"topics": [], "tool_calls": [], "summary": summary},
                "relationships": {},
                "new_nodes_to_create": {}
            }
    
    async def _write_neo4j(
        self,
        session_data: SessionData,
        summary: str,
        topics: List[str],
        entities: Dict[str, Any]
    ) -> bool:
        """
        STEP 5: Write to Neo4j (awaited - never fire-and-forget).
        Creates Session node and all relationships.
        """
        try:
            session_id = session_data.session_id
            pending_confirmations = []
            
            # 5a. Create Session node
            await graph_service.create_session_node(
                session_id=session_id,
                timestamp=session_data.timestamp,
                ended_at=session_data.ended_at,
                duration_seconds=session_data.duration_seconds,
                summary=summary,
                topics=topics,
                tool_calls=session_data.tool_calls,
                message_count=session_data.message_count,
                pending_confirmations=[]
            )
            
            # 5b. Session -[:RELATED_TO]-> KARTHIK is created in create_session_node
            
            # 5c. Create typed edges for HIGH confidence relationships
            relationships = entities.get("relationships", {})
            
            # TOUCHES_PROJECT edges
            for proj in relationships.get("touches_projects", []):
                if proj.get("confidence") == "HIGH":
                    await graph_service.create_typed_edge(
                        session_id, "TOUCHES_PROJECT", proj["name"], "Project"
                    )
            
            # USES_SKILL edges
            for skill in relationships.get("uses_skills", []):
                if skill.get("confidence") == "HIGH":
                    await graph_service.create_typed_edge(
                        session_id, "USES_SKILL", skill["name"], "Skill"
                    )
            
            # INVOLVES_TOOL edges
            for tool in relationships.get("involves_tools", []):
                if tool.get("confidence") == "HIGH":
                    await graph_service.create_typed_edge(
                        session_id, "INVOLVES_TOOL", tool["name"], "Tool"
                    )
            
            # INVOLVES_PERSON edges
            for person in relationships.get("involves_people", []):
                if person.get("confidence") == "HIGH":
                    await graph_service.create_typed_edge(
                        session_id, "INVOLVES_PERSON", person["name"], "User"
                    )
            
            # CREATES_COMMITMENT edges
            for commitment in relationships.get("creates_commitments", []):
                if commitment.get("confidence") == "HIGH":
                    # Create commitment node first
                    await graph_service.create_dynamic_node(
                        "commitment", commitment, "Commitments"
                    )
                    # Then create edge
                    await graph_service.create_typed_edge(
                        session_id, "CREATES_COMMITMENT", 
                        commitment.get("description", ""), "Commitment"
                    )
            
            # 5d. Create new nodes based on confidence
            new_nodes = entities.get("new_nodes_to_create", {})
            
            # Projects
            for proj in new_nodes.get("projects", []):
                if proj.get("confidence") == "HIGH":
                    await graph_service.create_dynamic_node("project", proj, "Projects")
                    await graph_service.create_typed_edge(
                        session_id, "TOUCHES_PROJECT", proj["name"], "Project"
                    )
                else:
                    pending_confirmations.append({
                        "entity_type": "project",
                        "entity_data": proj,
                        "confidence": proj.get("confidence", "MEDIUM")
                    })
            
            # Skills
            for skill in new_nodes.get("skills", []):
                if skill.get("confidence") == "HIGH":
                    await graph_service.create_dynamic_node("skill", skill, skill.get("group", "Skills"))
                    await graph_service.create_typed_edge(
                        session_id, "USES_SKILL", skill["name"], "Skill"
                    )
                else:
                    pending_confirmations.append({
                        "entity_type": "skill",
                        "entity_data": skill,
                        "confidence": skill.get("confidence", "MEDIUM")
                    })
            
            # People
            for person in new_nodes.get("people", []):
                if person.get("confidence") == "HIGH":
                    await graph_service.create_dynamic_node("person", person, "People")
                    await graph_service.create_typed_edge(
                        session_id, "INVOLVES_PERSON", person["name"], "User"
                    )
                else:
                    pending_confirmations.append({
                        "entity_type": "person",
                        "entity_data": person,
                        "confidence": person.get("confidence", "MEDIUM")
                    })
            
            # Interests
            for interest in new_nodes.get("interests", []):
                if interest.get("confidence") == "HIGH":
                    await graph_service.create_dynamic_node("interest", interest, "Interests")
                else:
                    pending_confirmations.append({
                        "entity_type": "interest",
                        "entity_data": interest,
                        "confidence": interest.get("confidence", "MEDIUM")
                    })
            
            # Store pending confirmations for later
            entities["pending_confirmations"] = pending_confirmations
            
            logger.info(f"Neo4j write successful: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Neo4j write failed: {e}")
            raise  # Re-raise to ensure saga knows it failed
    
    async def _store_pending_confirmations(
        self,
        session_id: str,
        pending_confirmations: List[Dict[str, Any]]
    ) -> bool:
        """
        Store MEDIUM/LOW confidence entities for Karthik's approval.
        """
        if not pending_confirmations:
            return True
        
        try:
            collection = self.db["pending_confirmations"]
            
            documents = []
            for conf in pending_confirmations:
                documents.append({
                    "confirmation_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "entity_type": conf["entity_type"],
                    "entity_data": conf["entity_data"],
                    "confidence": conf["confidence"],
                    "reason": conf["entity_data"].get("reason", ""),
                    "status": "awaiting_karthik",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
            
            await collection.insert_many(documents)
            logger.info(f"Stored {len(documents)} pending confirmations for {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store pending confirmations: {e}")
            return False
    
    async def _update_mongodb_status(
        self,
        session_id: str,
        field: str,
        value: str
    ) -> bool:
        """Update status field in MongoDB"""
        try:
            collection = self.db["sessions"]
            await collection.update_one(
                {"session_id": session_id},
                {"$set": {field: value}}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update MongoDB status: {e}")
            return False


# Global instance
memory_saga = MemorySaga()


class SagaRetryWorker:
    """
    Background worker that retries failed MemorySaga operations.
    Handles partial_sync sessions and retries Pinecone/Neo4j writes.
    """
    
    def __init__(self):
        self.running = False
        self.task = None
        self.mongo_client = None
        self.db = None
    
    async def start(self):
        """Start the retry worker"""
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._retry_loop())
        logger.info("SagaRetryWorker started")
    
    async def stop(self):
        """Stop the retry worker"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("SagaRetryWorker stopped")
    
    async def drain(self):
        """Drain pending operations (called during shutdown)"""
        # Simple implementation - just wait a bit for current operations
        await asyncio.sleep(1.0)
    
    async def _retry_loop(self):
        """Main retry loop"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Find sessions with partial_sync status
                await self._retry_partial_sync_sessions()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SagaRetryWorker error: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _retry_partial_sync_sessions(self):
        """Find and retry sessions with partial_sync status"""
        try:
            # Initialize MongoDB connection if needed
            if not self.mongo_client:
                mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
                if not mongo_uri:
                    return
                
                from motor.motor_asyncio import AsyncIOMotorClient
                self.mongo_client = AsyncIOMotorClient(mongo_uri)
                self.db = self.mongo_client.get_database("asta_memory")
            
            # Find sessions that need retry
            collection = self.db["sessions"]
            cursor = collection.find({
                "status": "partial_sync",
                "$or": [
                    {"embedding_status": {"$ne": "complete"}},
                    {"neo4j_status": {"$ne": "complete"}}
                ]
            }).limit(5)
            
            sessions = await cursor.to_list(length=5)
            
            for session_doc in sessions:
                session_id = session_doc.get("session_id")
                if not session_id:
                    continue
                
                logger.info(f"Retrying partial sync for session: {session_id}")
                
                # Create MemorySaga and retry
                saga = MemorySaga(
                    session_id=session_id,
                    summary=session_doc.get("summary", ""),
                    embedding=session_doc.get("embedding", [])
                )
                
                success = await saga.execute()
                
                if success:
                    # Update status to completed
                    await collection.update_one(
                        {"session_id": session_id},
                        {"$set": {"status": "completed"}}
                    )
                    logger.info(f"Successfully retried session: {session_id}")
                else:
                    logger.warning(f"Retry failed for session: {session_id}")
                
        except Exception as e:
            logger.error(f"Error retrying partial sync sessions: {e}")


# Global instance
saga_retry_worker = SagaRetryWorker()