# Memory Layer Implementation Template

## Quick Start for New Projects

This template shows you how to implement the same memory architecture in any project.

---

## Minimal Implementation (3 Files)

### 1. `memory_config.py` - Configuration

```python
from pydantic_settings import BaseSettings

class MemorySettings(BaseSettings):
    # Redis (L1 Cache)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_HOT: int = 3600
    REDIS_TTL_ENTITY: int = 86400
    
    # MongoDB (L4 Store)
    MONGO_URI: str
    DB_NAME: str = "memory_db"
    
    # Neo4j (L2 Graph)
    NEO4J_URI: str
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str
    
    # Pinecone (L3 Vectors)
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "memory-index"
    
    # Embeddings
    GEMINI_API_KEY: str
    
    # Entity Extraction
    GROQ_API_KEY: str
    
    # Tuning
    MEMORY_TOP_K: int = 3
    MEMORY_CLUSTER_DEPTH: int = 2
    
    class Config:
        env_file = ".env"

settings = MemorySettings()
```

### 2. `memory_core.py` - Core Memory Engine

```python
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from pinecone import Pinecone
import google.generativeai as genai

logger = logging.getLogger(__name__)

class MemoryCore:
    """
    Minimal memory engine with 4 layers:
    L1 (Redis) → L2 (Neo4j) → L3 (Pinecone) → L4 (MongoDB)
    """
    
    def __init__(self, settings):
        self.settings = settings
        
        # Clients
        self.redis_client = None
        self.mongo_client = None
        self.neo4j_driver = None
        self.pinecone_index = None
        
    async def connect(self):
        """Initialize all connections"""
        # Redis
        self.redis_client = redis.from_url(
            self.settings.REDIS_URL,
            decode_responses=True
        )
        await self.redis_client.ping()
        
        # MongoDB
        self.mongo_client = AsyncIOMotorClient(self.settings.MONGO_URI)
        self.db = self.mongo_client[self.settings.DB_NAME]
        await self.mongo_client.admin.command('ping')
        
        # Neo4j
        self.neo4j_driver = AsyncGraphDatabase.driver(
            self.settings.NEO4J_URI,
            auth=(self.settings.NEO4J_USERNAME, self.settings.NEO4J_PASSWORD)
        )
        
        # Pinecone
        pc = Pinecone(api_key=self.settings.PINECONE_API_KEY)
        self.pinecone_index = pc.Index(self.settings.PINECONE_INDEX_NAME)
        
        # Google AI for embeddings
        genai.configure(api_key=self.settings.GEMINI_API_KEY)
        
        logger.info("Memory layers connected")
    
    # ═══ RETRIEVAL ═══════════════════════════════════════════════════
    
    async def get_context(self, session_id: str, query: str) -> Dict:
        """
        Main retrieval method.
        Returns relevant past sessions for context injection.
        """
        # 1. Check L1 cache
        cached = await self._get_from_cache(f"context:{session_id}")
        if cached:
            return {"sessions": cached, "from_cache": True}
        
        # 2. Spot entities in query
        entities = await self._spot_entities(query)
        
        # 3. Get cluster from Neo4j
        cluster_ids = await self._get_cluster(entities)
        
        # 4. Vector search in Pinecone
        vector_results = await self._vector_search(query, cluster_ids)
        
        # 5. Fetch full sessions from MongoDB
        sessions = await self._fetch_sessions(vector_results)
        
        # 6. Cache result
        await self._set_cache(f"context:{session_id}", sessions, ttl=3600)
        
        return {"sessions": sessions, "from_cache": False}
    
    async def _spot_entities(self, text: str) -> List[str]:
        """Extract entity names from text"""
        # Simple implementation - you can enhance with NER
        async with self.neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (e) WHERE e.name IS NOT NULL RETURN e.name as name"
            )
            known_entities = [record["name"] async for record in result]
        
        # Find which entities are mentioned in text
        spotted = [e for e in known_entities if e.lower() in text.lower()]
        return spotted[:5]  # Limit to 5
    
    async def _get_cluster(self, entities: List[str]) -> List[str]:
        """Get related session IDs from Neo4j graph"""
        if not entities:
            return []
        
        async with self.neo4j_driver.session() as session:
            query = f"""
            MATCH (e)-[:RELATED_TO*0..{self.settings.MEMORY_CLUSTER_DEPTH}]-(related)
            WHERE e.name IN $entities
            MATCH (s:Session)-[:COVERS]->(related)
            RETURN DISTINCT s.session_id as session_id
            LIMIT 50
            """
            result = await session.run(query, entities=entities)
            return [record["session_id"] async for record in result]
    
    async def _vector_search(self, query: str, filter_ids: List[str] = None) -> List[Dict]:
        """Semantic search in Pinecone"""
        # Generate embedding
        embedding = await self._embed(query)
        
        # Build filter
        filter_dict = None
        if filter_ids:
            filter_dict = {"session_id": {"$in": filter_ids}}
        
        # Query
        def _query():
            return self.pinecone_index.query(
                vector=embedding,
                top_k=self.settings.MEMORY_TOP_K,
                filter=filter_dict,
                include_metadata=True
            )
        
        results = await asyncio.to_thread(_query)
        
        return [
            {
                "session_id": match.metadata.get("session_id"),
                "score": float(match.score)
            }
            for match in results.matches
        ]
    
    async def _fetch_sessions(self, vector_results: List[Dict]) -> List[Dict]:
        """Fetch full session documents from MongoDB"""
        session_ids = [r["session_id"] for r in vector_results]
        
        cursor = self.db.sessions.find(
            {"session_id": {"$in": session_ids}},
            {"session_id": 1, "summary": 1, "entities": 1, "end_time": 1, "_id": 0}
        )
        
        return await cursor.to_list(length=None)
    
    # ═══ STORAGE ═════════════════════════════════════════════════════
    
    async def save_session(self, session_id: str, messages: List[Dict], 
                          entities: List[str], summary: str):
        """
        Save session to all layers.
        """
        # 1. MongoDB (required)
        await self.db.sessions.insert_one({
            "session_id": session_id,
            "messages": messages,
            "summary": summary,
            "entities": entities,
            "end_time": datetime.utcnow().isoformat()
        })
        
        # 2. Pinecone (vector)
        embedding = await self._embed(summary)
        
        def _upsert():
            self.pinecone_index.upsert(
                vectors=[{
                    "id": session_id,
                    "values": embedding,
                    "metadata": {
                        "session_id": session_id,
                        "entities": ",".join(entities)
                    }
                }]
            )
        
        await asyncio.to_thread(_upsert)
        
        # 3. Neo4j (graph)
        async with self.neo4j_driver.session() as session:
            # Create session node
            await session.run(
                """
                MERGE (s:Session {session_id: $sid})
                SET s.summary = $summary, s.created_at = datetime()
                """,
                sid=session_id, summary=summary
            )
            
            # Link to entities
            for entity in entities:
                await session.run(
                    """
                    MERGE (e {name: $name})
                    WITH e
                    MATCH (s:Session {session_id: $sid})
                    MERGE (s)-[:COVERS]->(e)
                    """,
                    name=entity, sid=session_id
                )
        
        # 4. Invalidate cache
        await self.redis_client.delete(f"context:{session_id}")
        
        logger.info(f"Session {session_id} saved to all layers")
    
    # ═══ UTILITIES ═══════════════════════════════════════════════════
    
    async def _embed(self, text: str) -> List[float]:
        """Generate embedding using Google AI"""
        def _generate():
            result = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        
        return await asyncio.to_thread(_generate)
    
    async def _get_from_cache(self, key: str) -> Optional[any]:
        """Get from Redis cache"""
        data = await self.redis_client.get(key)
        if data:
            import json
            return json.loads(data)
        return None
    
    async def _set_cache(self, key: str, value: any, ttl: int):
        """Set in Redis cache"""
        import json
        await self.redis_client.setex(key, ttl, json.dumps(value))
    
    async def disconnect(self):
        """Close all connections"""
        if self.redis_client:
            await self.redis_client.aclose()
        if self.mongo_client:
            self.mongo_client.close()
        if self.neo4j_driver:
            await self.neo4j_driver.close()

# Global instance
memory = MemoryCore(settings)
```

### 3. `app.py` - Integration Example

```python
from fastapi import FastAPI, WebSocket
from memory_core import memory
from memory_config import settings

app = FastAPI()

@app.on_event("startup")
async def startup():
    await memory.connect()
    print("Memory layers ready")

@app.on_event("shutdown")
async def shutdown():
    await memory.disconnect()

@app.websocket("/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = generate_session_id()
    messages = []
    
    try:
        while True:
            # Receive message
            user_message = await websocket.receive_text()
            messages.append({"role": "user", "content": user_message})
            
            # Get context from memory
            context = await memory.get_context(session_id, user_message)
            
            # Format context for LLM
            context_str = format_context(context["sessions"])
            
            # Call your LLM
            response = await call_llm(user_message, context_str)
            messages.append({"role": "assistant", "content": response})
            
            # Send response
            await websocket.send_text(response)
            
    except WebSocketDisconnect:
        # Save session on disconnect
        summary = await generate_summary(messages)
        entities = await extract_entities(messages)
        
        await memory.save_session(
            session_id=session_id,
            messages=messages,
            entities=entities,
            summary=summary
        )

def format_context(sessions: List[Dict]) -> str:
    """Format retrieved sessions for LLM prompt"""
    if not sessions:
        return ""
    
    lines = ["--- RELEVANT PAST CONTEXT ---"]
    for s in sessions:
        lines.append(f"\n[{s['end_time'][:10]}]")
        lines.append(s['summary'])
    lines.append("--- END CONTEXT ---")
    
    return "\n".join(lines)
```

---

## Advanced Features (Optional)

### Entity Extraction with Groq

```python
from groq import AsyncGroq

async def extract_entities(messages: List[Dict]) -> List[str]:
    """Extract entities using Groq LLM"""
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    
    conversation = "\n".join([
        f"{m['role']}: {m['content']}" for m in messages
    ])
    
    prompt = f"""Extract key entities (people, projects, topics) from this conversation.
Return as JSON array of strings.

Conversation:
{conversation}

Entities:"""
    
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    import json
    result = json.loads(response.choices[0].message.content)
    return result.get("entities", [])
```

### Summary Generation with TextRank

```python
from summa import summarizer

def generate_summary(messages: List[Dict]) -> str:
    """Generate extractive summary using TextRank"""
    conversation = "\n\n".join([
        f"{m['role'].upper()}: {m['content']}" for m in messages
    ])
    
    # Extract key sentences (30% of original)
    summary = summarizer.summarize(conversation, ratio=0.3)
    
    # Fallback to first 300 chars if TextRank fails
    if not summary:
        summary = conversation[:300]
    
    return summary
```

### Speculative Prefetch

```python
class PrefetchEngine:
    """Background entity prefetching"""
    
    def __init__(self, memory_core):
        self.memory = memory_core
        self.queue = asyncio.Queue()
        self.task = None
    
    async def start(self):
        """Start background worker"""
        self.task = asyncio.create_task(self._worker())
    
    async def prefetch(self, session_id: str, partial_text: str):
        """Queue a prefetch request"""
        await self.queue.put((session_id, partial_text))
    
    async def _worker(self):
        """Background worker that processes prefetch queue"""
        while True:
            session_id, text = await self.queue.get()
            
            try:
                # Spot entities
                entities = await self.memory._spot_entities(text)
                
                # For each entity, fetch and cache context
                for entity in entities:
                    cluster_ids = await self.memory._get_cluster([entity])
                    vector_results = await self.memory._vector_search(text, cluster_ids)
                    sessions = await self.memory._fetch_sessions(vector_results)
                    
                    # Cache entity context
                    await self.memory._set_cache(
                        f"entity:{entity}",
                        sessions,
                        ttl=self.memory.settings.REDIS_TTL_ENTITY
                    )
                
            except Exception as e:
                logger.error(f"Prefetch failed: {e}")
            
            self.queue.task_done()

# Usage in WebSocket
prefetch = PrefetchEngine(memory)

@app.on_event("startup")
async def startup():
    await memory.connect()
    await prefetch.start()

# In your STT callback
async def on_partial_transcript(session_id: str, text: str):
    """Called when STT returns non-final transcript"""
    await prefetch.prefetch(session_id, text)
```

---

## Database Setup Scripts

### MongoDB Indexes

```python
async def setup_mongodb_indexes():
    """Create required indexes"""
    await memory.db.sessions.create_index([("session_id", 1)], unique=True)
    await memory.db.sessions.create_index([("entities", 1)])
    await memory.db.sessions.create_index([("end_time", 1)])
```

### Neo4j Schema

```python
async def setup_neo4j_schema():
    """Initialize Neo4j schema"""
    async with memory.neo4j_driver.session() as session:
        # Create root user node
        await session.run("""
            MERGE (u:User {name: $name})
            ON CREATE SET u.created_at = datetime()
        """, name="YOUR_USER_NAME")
        
        # Create indexes
        await session.run("""
            CREATE INDEX entity_name IF NOT EXISTS FOR (n) ON (n.name)
        """)
        
        await session.run("""
            CREATE INDEX session_id IF NOT EXISTS FOR (n:Session) ON (n.session_id)
        """)
```

### Pinecone Index

```python
from pinecone import Pinecone, ServerlessSpec

def setup_pinecone_index():
    """Create Pinecone index (run once)"""
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    
    # Check if exists
    if settings.PINECONE_INDEX_NAME not in [idx.name for idx in pc.list_indexes()]:
        pc.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=3072,  # gemini-embedding-001
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        print(f"Created index: {settings.PINECONE_INDEX_NAME}")
```

---

## Testing

```python
import pytest

@pytest.mark.asyncio
async def test_memory_retrieval():
    """Test basic retrieval flow"""
    await memory.connect()
    
    # Save a test session
    await memory.save_session(
        session_id="test-123",
        messages=[
            {"role": "user", "content": "Tell me about Python"},
            {"role": "assistant", "content": "Python is a programming language..."}
        ],
        entities=["Python", "programming"],
        summary="Discussion about Python programming language"
    )
    
    # Retrieve context
    context = await memory.get_context("test-456", "What is Python?")
    
    assert len(context["sessions"]) > 0
    assert context["sessions"][0]["session_id"] == "test-123"
    
    await memory.disconnect()
```

---

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: password

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - MONGO_URI=mongodb://admin:password@mongodb:27017/
      - NEO4J_URI=${NEO4J_URI}
      - PINECONE_API_KEY=${PINECONE_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    depends_on:
      - redis
      - mongodb
```

---

## Summary

This minimal implementation gives you:

1. **4-layer memory architecture** (Redis → Neo4j → Pinecone → MongoDB)
2. **Fast retrieval** with caching
3. **Semantic search** with embeddings
4. **Entity relationships** via graph
5. **Session persistence** with full history

Total code: ~500 lines across 3 files.

You can extend it with:
- Entity extraction (Groq)
- Summary generation (TextRank)
- Speculative prefetch
- Retry logic
- Monitoring

The architecture is the same as ASTA's production system, just simplified for easier adoption.
