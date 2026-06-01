"""
ASTA Memory Engine - Simplified Version for Backend Core
Handles cross-session memory retrieval and storage using Neo4j, Pinecone, and MongoDB.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from app.db import mongo_client, pinecone_client, neo4j_client
from app.core.llm_router import llm_router
from app.config import settings

logger = logging.getLogger(__name__)

class MemoryEngine:
    """
    Memory engine for ASTA - handles retrieval and storage of cross-session memory.
    Uses Neo4j for topic clustering, Pinecone for vector search, MongoDB for storage.
    """
    
    async def retrieve_context(self, current_input: str, current_topics: List[str]) -> List[Dict]:
        """
        Called at start of every session. Returns relevant past session summaries.
        
        Pipeline:
        1. Neo4j — get related topic clusters
        2. Pinecone — vector search with topic filter
        3. MongoDB — fetch full summaries
        4. Return formatted context
        """
        try:
            # Step 1: Get related topics from Neo4j
            related_topics = []
            if current_topics:
                try:
                    related_topics = await neo4j_client.get_related_topic_clusters(
                        current_topics, depth=2
                    )
                except Exception as e:
                    logger.warning(f"Neo4j topic clustering failed: {e}")
                    related_topics = current_topics
            
            # Step 2: Vector search in Pinecone
            vector_results = []
            try:
                # Generate embedding for current input
                embedding = await self._generate_embedding(current_input)
                
                # Search with topic filter if we have related topics
                filter_dict = {}
                if related_topics:
                    filter_dict = {"topics": {"$in": related_topics}}
                
                vector_results = await pinecone_client.query_vectors(
                    embedding=embedding,
                    top_k=3,
                    filter=filter_dict
                )
            except Exception as e:
                logger.warning(f"Pinecone vector search failed: {e}")
            
            # Step 3: Fetch full sessions from MongoDB
            session_summaries = []
            if vector_results:
                try:
                    session_ids = [result.get("id") for result in vector_results if result.get("id")]
                    if session_ids:
                        sessions = await mongo_client.sessions.find(
                            {"session_id": {"$in": session_ids}}
                        ).to_list(length=10)
                        
                        for session in sessions:
                            session_summaries.append({
                                "session_id": session.get("session_id"),
                                "date": session.get("end_time", "")[:10],
                                "workflow_type": session.get("workflow_type"),
                                "summary": session.get("summary", ""),
                                "topics": session.get("topics", [])
                            })
                except Exception as e:
                    logger.warning(f"MongoDB session fetch failed: {e}")
            
            logger.info(f"Retrieved {len(session_summaries)} relevant sessions")
            return session_summaries
            
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return []
    
    async def save_session(self, session_data: Dict) -> bool:
        """
        Called at end of every session. Saves to all three databases.
        
        session_data keys: session_id, workflow_type, messages, summary, topics, start_time, end_time
        """
        try:
            session_id = session_data["session_id"]
            workflow_type = session_data["workflow_type"]
            messages = session_data["messages"]
            summary = session_data["summary"]
            topics = session_data.get("topics", [])
            start_time = session_data.get("start_time")
            end_time = session_data.get("end_time", datetime.utcnow().isoformat())
            
            # Step 1: Save to MongoDB
            session_doc = {
                "session_id": session_id,
                "workflow_type": workflow_type,
                "messages": messages,
                "summary": summary,
                "topics": topics,
                "start_time": start_time,
                "end_time": end_time,
                "created_at": datetime.utcnow()
            }
            
            await mongo_client.sessions.insert_one(session_doc)
            logger.info(f"Session {session_id} saved to MongoDB")
            
            # Step 2: Generate embedding and save to Pinecone
            try:
                embedding = await self._generate_embedding(summary)
                metadata = {
                    "session_id": session_id,
                    "workflow_type": workflow_type,
                    "date": end_time[:10],
                    "topics": ",".join(topics),
                    "summary_snippet": summary[:200]
                }
                
                await pinecone_client.upsert_vectors([{
                    "id": session_id,
                    "values": embedding,
                    "metadata": metadata
                }])
                logger.info(f"Session {session_id} saved to Pinecone")
            except Exception as e:
                logger.warning(f"Pinecone save failed: {e}")
            
            # Step 3: Save topics and relationships to Neo4j
            try:
                for topic in topics:
                    await neo4j_client.upsert_topic(topic, "TOPIC")
                
                if topics:
                    await neo4j_client.link_session_to_topics(session_id, topics)
                
                logger.info(f"Session {session_id} linked to topics in Neo4j")
            except Exception as e:
                logger.warning(f"Neo4j save failed: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
    
    async def generate_session_summary(self, messages: List, workflow_type: str) -> str:
        """
        Generate a summary of the session using LLM.
        """
        try:
            # Convert messages to text
            conversation_text = ""
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                conversation_text += f"{role}: {content}\n"
            
            # Generate summary using LLM
            prompt = f"""Summarize this {workflow_type} conversation in 3-5 bullet points. 
Focus on: decisions made, topics discussed, tasks created, key insights.

Conversation:
{conversation_text}

Summary:"""
            
            llm = llm_router.get_llm("quick_classification")
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate session summary: {e}")
            return f"Session summary unavailable: {str(e)}"
    
    async def save_permanent_memory(self, content: str, tags: List[str]) -> Dict:
        """Save content to permanent memory collection."""
        try:
            memory_doc = {
                "content": content,
                "tags": tags,
                "created_at": datetime.utcnow(),
                "recalled_count": 0
            }
            
            result = await mongo_client.permanent_memory.insert_one(memory_doc)
            memory_doc["memory_id"] = str(result.inserted_id)
            
            # Also save to Pinecone for semantic search
            try:
                embedding = await self._generate_embedding(content)
                await pinecone_client.upsert_vectors([{
                    "id": f"permanent_{result.inserted_id}",
                    "values": embedding,
                    "metadata": {
                        "type": "permanent",
                        "tags": ",".join(tags),
                        "content_snippet": content[:200]
                    }
                }])
            except Exception as e:
                logger.warning(f"Failed to save permanent memory to Pinecone: {e}")
            
            logger.info(f"Permanent memory saved: {result.inserted_id}")
            return memory_doc
            
        except Exception as e:
            logger.error(f"Failed to save permanent memory: {e}")
            return {}
    
    async def recall_permanent_memory(self, query: str) -> List[Dict]:
        """Semantic search in permanent memory."""
        try:
            # Vector search in Pinecone
            embedding = await self._generate_embedding(query)
            results = await pinecone_client.query_vectors(
                embedding=embedding,
                top_k=5,
                filter={"type": "permanent"}
            )
            
            # Get full documents from MongoDB
            memory_ids = []
            for result in results:
                if result.get("id", "").startswith("permanent_"):
                    memory_id = result["id"].replace("permanent_", "")
                    memory_ids.append(memory_id)
            
            if memory_ids:
                from bson import ObjectId
                memories = await mongo_client.permanent_memory.find(
                    {"_id": {"$in": [ObjectId(mid) for mid in memory_ids]}}
                ).to_list(length=10)
                
                return memories
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to recall permanent memory: {e}")
            return []
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using Google's text-embedding model."""
        try:
            # Use Google's embedding model through LangChain
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            
            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=settings.GEMINI_API_KEY
            )
            
            embedding = await embeddings.aembed_query(text)
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # Return a dummy embedding of the right size (768 dimensions for text-embedding-004)
            return [0.0] * 768

# Export singleton
memory_engine = MemoryEngine()