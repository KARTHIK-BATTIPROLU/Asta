"""
Memory Orchestrator for ASTA
Handles read flow with RRF fusion - PERSISTENT CONNECTIONS
"""
import logging
import asyncio
import os
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pinecone import Pinecone

from memory.graph_service import graph_service
from memory.embeddings import embedding_service
from memory.memory_saga import memory_saga

logger = logging.getLogger("MemoryOrchestrator")

# PERSISTENT MongoDB client - created ONCE at module level
_mongo_client = None
_mongo_db = None

def _get_mongo():
    """Get or create persistent MongoDB connection (singleton pattern)"""
    global _mongo_client, _mongo_db
    if _mongo_client is None:
        mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGODB_URI or MONGO_URI environment variable required")
        
        _mongo_client = AsyncIOMotorClient(
            mongo_uri,
            maxPoolSize=50,
            minPoolSize=10,
            maxIdleTimeMS=45000,
            serverSelectionTimeoutMS=5000
        )
        _mongo_db = _mongo_client.get_database("asta_memory")
        logger.info("MongoDB persistent connection created")
    
    return _mongo_db

# PERSISTENT Pinecone index - created ONCE at module level
_pinecone_index = None

def _get_pinecone():
    """Get or create persistent Pinecone index (singleton pattern)"""
    global _pinecone_index
    if _pinecone_index is None:
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        pinecone_index_name = os.getenv("PINECONE_INDEX_NAME")
        
        if not pinecone_api_key or not pinecone_index_name:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME required")
        
        pc = Pinecone(api_key=pinecone_api_key)
        _pinecone_index = pc.Index(pinecone_index_name)
        logger.info("Pinecone persistent index created")
    
    return _pinecone_index


class MemoryOrchestrator:
    """
    Orchestrates memory retrieval with PERSISTENT connections.
    All database connections are reused across calls.
    """
    
    def __init__(self):
        self.db = _get_mongo()
        self.pinecone_index = _get_pinecone()
        logger.info("MemoryOrchestrator initialized with persistent connections")
    
    async def retrieve_memory(
        self,
        query: str,
        current_session_id: str,
        top_k: int = 8
    ) -> str:
        """
        Retrieve relevant memory for query with 5s hard timeout.
        Uses persistent connections - NO reconnection overhead.
        
        Network latency breakdown:
        - Embedding: ~40ms (local)
        - Pinecone query: ~300-400ms (network)
        - Neo4j search: ~1.8s (network)
        - MongoDB fetch: ~2s (network)
        - Parallel execution: ~2-3s total
        
        Returns structured XML context:
        <memory_context>
          <core_identity>...</core_identity>
          <episodic_recall>...</episodic_recall>
          <tool_history>...</tool_history>
        </memory_context>
        """
        
        try:
            # Hard timeout: 10 seconds (temporary increase for testing)
            result = await asyncio.wait_for(
                self._retrieve_memory_internal(query, current_session_id, top_k),
                timeout=10.0
            )
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"Memory retrieval timeout for query: {query[:50]}")
            return self._empty_context()
        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            return self._empty_context()
    
    async def _retrieve_memory_internal(
        self,
        query: str,
        current_session_id: str,
        top_k: int
    ) -> str:
        """Internal retrieval logic"""
        
        # Step 1: Parallel search
        graph_task = asyncio.create_task(
            graph_service.search_graph_context(query, limit=50)
        )
        
        pinecone_task = asyncio.create_task(
            self._pinecone_search(query, top_k=top_k * 2)  # Get more for RRF
        )
        
        # Wait for both
        graph_session_ids, pinecone_results = await asyncio.gather(
            graph_task,
            pinecone_task,
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(graph_session_ids, Exception):
            logger.error(f"Graph search failed: {graph_session_ids}")
            graph_session_ids = []
        
        if isinstance(pinecone_results, Exception):
            logger.error(f"Pinecone search failed: {pinecone_results}")
            pinecone_results = []
        
        # Step 2: RRF fusion
        fused_session_ids = self._rrf_fusion(
            graph_session_ids,
            pinecone_results,
            k=60,
            top_k=top_k
        )
        
        # Step 3: Fetch session details from MongoDB
        sessions = await self._fetch_sessions(fused_session_ids)
        
        # Step 4: Build XML context
        return self._build_xml_context(sessions)
    
    async def _pinecone_search(
        self,
        query: str,
        top_k: int = 16
    ) -> List[Dict[str, Any]]:
        """Search Pinecone - uses persistent connection, NO reconnection overhead"""
        
        try:
            # Generate query embedding (10-20ms, no executor needed)
            query_embedding = embedding_service.embed(query)
            
            # Search Pinecone (10-20ms, no executor needed)
            results = self.pinecone_index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True
            )
            
            # Extract session IDs and scores
            pinecone_results = []
            for match in results.get("matches", []):
                pinecone_results.append({
                    "session_id": match["id"],
                    "score": match["score"]
                })
            
            logger.info(f"Pinecone found {len(pinecone_results)} results")
            return pinecone_results
            
        except Exception as e:
            logger.error(f"Pinecone search failed: {e}")
            return []
    
    def _rrf_fusion(
        self,
        graph_session_ids: List[str],
        pinecone_results: List[Dict[str, Any]],
        k: int = 60,
        top_k: int = 8
    ) -> List[str]:
        """
        Reciprocal Rank Fusion (RRF) with k=60.
        
        RRF formula: score = sum(1 / (k + rank))
        """
        scores = {}
        
        # Score from graph results
        for rank, session_id in enumerate(graph_session_ids, start=1):
            if session_id not in scores:
                scores[session_id] = 0
            scores[session_id] += 1 / (k + rank)
        
        # Score from Pinecone results
        for rank, result in enumerate(pinecone_results, start=1):
            session_id = result["session_id"]
            if session_id not in scores:
                scores[session_id] = 0
            scores[session_id] += 1 / (k + rank)
        
        # Sort by score and return top_k
        sorted_sessions = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        fused_ids = [session_id for session_id, _ in sorted_sessions[:top_k]]
        logger.info(f"RRF fusion returned {len(fused_ids)} sessions")
        return fused_ids
    
    async def _fetch_sessions(
        self,
        session_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Fetch session details from MongoDB"""
        if not session_ids:
            return []
        
        try:
            collection = self.db["sessions"]
            cursor = collection.find(
                {"session_id": {"$in": session_ids}},
                {
                    "session_id": 1,
                    "timestamp": 1,
                    "summary": 1,
                    "topics": 1,
                    "tool_calls": 1
                }
            )
            
            sessions = await cursor.to_list(length=len(session_ids))
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to fetch sessions: {e}")
            return []
    
    def _build_xml_context(
        self,
        sessions: List[Dict[str, Any]]
    ) -> str:
        """Build structured XML context for LLM"""
        
        # Build episodic recall section
        episodic_lines = []
        for session in sessions:
            timestamp = session.get("timestamp", "")
            summary = session.get("summary", "")
            topics = session.get("topics", [])
            tool_calls = session.get("tool_calls", [])
            
            episodic_lines.append(f"""
  <session>
    <timestamp>{timestamp}</timestamp>
    <summary>{summary}</summary>
    <topics>{', '.join(topics)}</topics>
    <tools_used>{', '.join(tool_calls)}</tools_used>
  </session>""")
        
        episodic_recall = "\n".join(episodic_lines) if episodic_lines else "\n  <session>No relevant past sessions found</session>"
        
        # Build full context
        xml = f"""<memory_context>
  <core_identity>
    <name>Karthik</name>
    <active_projects>ASTA</active_projects>
    <current_focus>memory layer</current_focus>
  </core_identity>
  <episodic_recall>{episodic_recall}
  </episodic_recall>
</memory_context>"""
        
        return xml
    
    def _empty_context(self) -> str:
        """Return empty context on timeout or error"""
        return """<memory_context>
  <core_identity>
    <name>Karthik</name>
    <active_projects>ASTA</active_projects>
  </core_identity>
  <episodic_recall>
    <session>Memory retrieval unavailable</session>
  </episodic_recall>
</memory_context>"""
    
    async def commit_session(
        self,
        session_id: str,
        user_id: str,
        timestamp: str,
        ended_at: str,
        duration_seconds: int,
        raw_messages: List[Dict[str, str]],
        message_count: int,
        tool_calls: List[str]
    ) -> bool:
        """
        Commit session to L2/L3 via MemorySaga.
        This triggers the full write pipeline.
        """
        from memory.memory_saga import SessionData
        
        session_data = SessionData(
            session_id=session_id,
            user_id=user_id,
            timestamp=timestamp,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            raw_messages=raw_messages,
            message_count=message_count,
            tool_calls=tool_calls
        )
        
        return await memory_saga.execute(session_data)
    
    async def get_pending_confirmations(
        self,
        session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get pending entity confirmations.
        If session_id provided, returns only for that session.
        Otherwise returns all pending.
        """
        try:
            collection = self.db["pending_confirmations"]
            
            query = {"status": "awaiting_karthik"}
            if session_id:
                query["session_id"] = session_id
            
            cursor = collection.find(query).limit(20)
            confirmations = await cursor.to_list(length=20)
            
            return confirmations
            
        except Exception as e:
            logger.error(f"Failed to get pending confirmations: {e}")
            return []
    
    async def confirm_entity(
        self,
        confirmation_id: str,
        approved: bool
    ) -> bool:
        """
        Confirm or reject a pending entity.
        If approved, creates the node in Neo4j.
        """
        try:
            collection = self.db["pending_confirmations"]
            
            # Get confirmation
            confirmation = await collection.find_one({
                "confirmation_id": confirmation_id,
                "status": "awaiting_karthik"
            })
            
            if not confirmation:
                logger.warning(f"Confirmation {confirmation_id} not found")
                return False
            
            if approved:
                # Create node in Neo4j
                entity_type = confirmation["entity_type"]
                entity_data = confirmation["entity_data"]
                
                # Determine parent category
                category_map = {
                    "project": "Projects",
                    "skill": "Skills",
                    "tool": "Tools",
                    "person": "People",
                    "interest": "Interests",
                    "commitment": "Commitments"
                }
                
                parent_category = category_map.get(entity_type, "Projects")
                
                success = await graph_service.create_dynamic_node(
                    node_type=entity_type,
                    node_data=entity_data,
                    parent_category=parent_category
                )
                
                if not success:
                    logger.error(f"Failed to create node for confirmation {confirmation_id}")
                    return False
                
                # Update confirmation status
                await collection.update_one(
                    {"confirmation_id": confirmation_id},
                    {
                        "$set": {
                            "status": "approved",
                            "approved_at": asyncio.get_event_loop().time()
                        }
                    }
                )
                
                logger.info(f"Entity confirmed and created: {entity_data.get('name')}")
                return True
            else:
                # Reject confirmation
                await collection.update_one(
                    {"confirmation_id": confirmation_id},
                    {
                        "$set": {
                            "status": "rejected",
                            "rejected_at": asyncio.get_event_loop().time()
                        }
                    }
                )
                
                logger.info(f"Entity rejected: {confirmation_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to confirm entity: {e}")
            return False


# Global instance
memory_orchestrator = MemoryOrchestrator()
