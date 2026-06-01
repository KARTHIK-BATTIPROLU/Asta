# ASTA Memory Layer - Complete Architecture & Implementation Guide

## Table of Contents
1. [Overview](#overview)
2. [Architecture Layers](#architecture-layers)
3. [Data Flow](#data-flow)
4. [Persistence Layer](#persistence-layer)
5. [Implementation Guide](#implementation-guide)
6. [Configuration](#configuration)
7. [API Reference](#api-reference)
8. [Deployment](#deployment)

---

## Overview

ASTA's memory system is a **5-layer hierarchical architecture** designed for a personal AI assistant that remembers conversations, learns from interactions, and provides contextually relevant responses.

### Key Features
- **Multi-tier caching** (Redis → Neo4j → Pinecone → MongoDB)
- **Semantic search** with vector embeddings
- **Knowledge graph** for entity relationships
- **Atomic writes** with saga pattern
- **Speculative prefetching** for sub-200ms retrieval
- **Automatic entity extraction** from conversations

### Performance Targets
- **Retrieval**: <200ms (local), <500ms (cross-region)
- **Write**: Async, non-blocking with retry guarantees
- **Cache hit rate**: >80% for active sessions

---

## Architecture Layers

### L0 - In-Flight Context (LangGraph State)
**Purpose**: Current conversation state  
**Technology**: Python in-memory (LangGraph state)  
**Lifetime**: Single conversation turn  
**Size**: Current message + system prompt

### L1 - Hot Cache (Redis)
**Purpose**: Active session tracking and entity context  
**Technology**: Redis (async client)  
**Lifetime**: 1 hour (active sessions), 24 hours (entities)  
**Size**: ~100 active sessions, ~1000 entities

**Collections**:
```python
active_session:{session_id}     # Session metadata
entity_ctx:{entity_name}         # Pre-fetched entity context
retrieved_ctx:{session_id}       # Cached retrieval results
```

**Schema**:
```python
# Active Session
{
    "session_id": str,
    "workflow_type": str,
    "start_time": ISO datetime,
    "entities_seen": List[str]
}

# Entity Context
{
    "entity_name": str,
    "related_sessions": List[Dict],
    "last_updated": ISO datetime,
    "hit_count": int
}
```

### L1.5 - Speculative Prefetch Engine
**Purpose**: Background entity loading before user finishes speaking  
**Technology**: Async task queue  
**Trigger**: Non-final STT transcripts  
**Target**: 0ms perceived latency

**How it works**:
1. User starts speaking: "Tell me about the ASTA..."
2. Partial transcript triggers prefetch for "ASTA" entity
3. By the time user finishes, context is already in L1 cache
4. LLM gets instant context injection

### L2 - Knowledge Graph (Neo4j Aura)
**Purpose**: Entity relationships and identity layer  
**Technology**: Neo4j (async driver)  
**Lifetime**: Permanent  
**Size**: ~10K nodes, ~50K relationships

**Schema**:
```cypher
// Root node
(u:User {name: "KARTHIK"})

// Entity categories
(u)-[:HAS]->(category:Category {name: "Projects"})
(u)-[:HAS]->(category:Category {name: "Skills"})
(u)-[:HAS]->(category:Category {name: "People"})
(u)-[:HAS]->(category:Category {name: "Interests"})
(u)-[:HAS]->(category:Category {name: "Commitments"})

// Entities
(category)-[:CONTAINS]->(entity:Project|Skill|Person|Interest|Commitment)

// Sessions
(s:Session {session_id, timestamp, summary, topics})
(s)-[:RELATED_TO]->(u)
(s)-[:TOUCHES_PROJECT]->(p:Project)
(s)-[:USES_SKILL]->(sk:Skill)
(s)-[:INVOLVES_TOOL]->(t:Tool)
(s)-[:INVOLVES_PERSON]->(person:User)
(s)-[:CREATES_COMMITMENT]->(c:Commitment)

// Entity relationships
(entity1)-[:RELATED_TO]->(entity2)
```

**Key Queries**:
```cypher
// Get cluster of related sessions
MATCH (u:User {name: "KARTHIK"})-[:HAS]->(e)
WHERE e.name IN $entity_names
MATCH (s:Session)-[:COVERS]->(e)
RETURN DISTINCT s.session_id
UNION
MATCH (u:User {name: "KARTHIK"})-[:HAS]->(e1)-[:RELATED_TO*1..2]->(e2)
WHERE e1.name IN $entity_names
MATCH (s:Session)-[:COVERS]->(e2)
RETURN DISTINCT s.session_id
LIMIT 50
```

### L3 - Vector Store (Pinecone)
**Purpose**: Semantic search over session summaries  
**Technology**: Pinecone serverless  
**Lifetime**: Permanent  
**Size**: ~100K vectors

**Configuration**:
```python
Index: "asta-memory-v2"
Dimension: 3072  # Google gemini-embedding-001
Metric: cosine
Cloud: AWS us-east-1
```

**Vector Metadata**:
```python
{
    "session_id": str,
    "workflow_type": str,
    "end_time": ISO datetime,
    "topics": comma-separated string,
    "entity_names": comma-separated string,
    "summary_snippet": str (first 200 chars)
}
```

**Embedding Model**: Google `gemini-embedding-001` (3072 dimensions)

### L4 - Cold Store (MongoDB)
**Purpose**: Full session documents and permanent memory  
**Technology**: MongoDB Atlas (Motor async driver)  
**Lifetime**: 90 days (transcripts), permanent (summaries)  
**Size**: Unlimited

**Collections**:

#### `sessions`
```python
{
    "session_id": str (unique),
    "workflow_type": str,
    "start_time": ISO datetime,
    "end_time": ISO datetime,
    "summary": str,
    "entities": List[{
        "name": str,
        "entity_type": str,
        "description": str,
        "confidence": str
    }],
    "topics": List[str],
    "embedding_id": str,
    "notion_page_id": str,
    "raw_transcript": List[Dict],  # TTL: 90 days
    "raw_transcript_expires_at": datetime,
    "embedding_status": "pending" | "complete",
    "neo4j_status": "pending" | "complete",
    "created_at": datetime
}
```

#### `permanent_memory`
```python
{
    "memory_id": UUID,
    "content": str,
    "tags": List[str],
    "date_stored": ISO datetime,
    "recalled_count": int
}
```

#### `entities`
```python
{
    "name": str,
    "entity_type": str,
    "description": str,
    "confidence": str,
    "last_seen": ISO datetime
}
```

#### `pending_confirmations`
```python
{
    "confirmation_id": UUID,
    "session_id": str,
    "entity_type": str,
    "entity_data": Dict,
    "confidence": "MEDIUM" | "LOW",
    "reason": str,
    "status": "awaiting_karthik" | "approved" | "rejected",
    "created_at": datetime
}
```

---

## Data Flow

### Write Path (Session End)

```
Session End
    ↓
[Entity Extraction] (Groq llama-3.3-70b-versatile)
    ↓
[Summary Generation] (TextRank extractive)
    ↓
[Embedding Generation] (Google gemini-embedding-001)
    ↓
┌─────────────────────────────────────┐
│      Memory Saga (Atomic Write)     │
├─────────────────────────────────────┤
│ Phase 1: MongoDB (required)         │
│   ├─ Full session document          │
│   ├─ Status: embedding_status=pending│
│   └─ Status: neo4j_status=pending   │
│                                     │
│ Phase 2: Pinecone (retry on fail)  │
│   ├─ Upsert vector                  │
│   └─ Update: embedding_status=complete│
│                                     │
│ Phase 3: Neo4j (retry on fail)     │
│   ├─ Create Session node            │
│   ├─ Link to entities               │
│   ├─ Create new HIGH confidence nodes│
│   ├─ Store MEDIUM/LOW for approval  │
│   └─ Update: neo4j_status=complete  │
└─────────────────────────────────────┘
    ↓
[L1 Cache Invalidation]
    ↓
[Prefetch Engine Refresh]
```

### Read Path (Session Start)

```
User Query
    ↓
[Check L1 Retrieved Context Cache]
    ├─ HIT → Return cached context (0ms)
    └─ MISS ↓
         ↓
[Entity Spotting] (regex + known entities)
    ↓
[Check L1 Entity Context Cache]
    ├─ HIT → Use cached entity context
    └─ MISS ↓
         ↓
┌─────────────────────────────────────┐
│    Parallel Retrieval (1.5s timeout)│
├─────────────────────────────────────┤
│ Thread 1: Neo4j Cluster Search      │
│   └─ Get related session_ids        │
│                                     │
│ Thread 2: Pinecone Semantic Search  │
│   ├─ Embed query                    │
│   ├─ Filter by cluster_ids (if any) │
│   └─ Get top-K vectors              │
└─────────────────────────────────────┘
    ↓
[Late Fusion - Reciprocal Rank Fusion]
    ↓
[MongoDB Fetch Full Sessions]
    ↓
[Format as Structured XML]
    ↓
[Cache in L1 for this session]
    ↓
Return Context
```

### Speculative Prefetch Path

```
Partial STT Transcript
    ↓
[Intent Classification] (fast regex)
    ↓
[Entity Spotting]
    ↓
[Background Task Queue]
    ↓
┌─────────────────────────────────────┐
│   Prefetch Pipeline (async)         │
├─────────────────────────────────────┤
│ 1. Neo4j cluster search             │
│ 2. Pinecone vector search           │
│ 3. MongoDB fetch                    │
│ 4. Cache in L1 entity_ctx           │
└─────────────────────────────────────┘
    ↓
[Ready in L1 when user finishes speaking]
```

---

## Persistence Layer

### Database Connections

#### MongoDB (Motor Async)
```python
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(
    MONGO_URI,
    maxPoolSize=50,
    minPoolSize=5,
    serverSelectionTimeoutMS=20000,
    connectTimeoutMS=20000,
    socketTimeoutMS=30000,
    maxIdleTimeMS=45000,
    tlsAllowInvalidCertificates=True,
    retryWrites=True,
    retryReads=True,
    waitQueueTimeoutMS=10000
)

db = client[DB_NAME]
```

#### Neo4j (Async Driver)
```python
from neo4j import AsyncGraphDatabase

driver = AsyncGraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    connection_timeout=5.0
)
```

#### Pinecone (Serverless)
```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key=PINECONE_API_KEY)

# Create index (one-time)
pc.create_index(
    name=PINECONE_INDEX_NAME,
    dimension=3072,
    metric="cosine",
    spec=ServerlessSpec(
        cloud="aws",
        region="us-east-1"
    )
)

index = pc.Index(PINECONE_INDEX_NAME)
```

#### Redis (Async)
```python
import redis.asyncio as redis

client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)
```

### Indexes

#### MongoDB Indexes
```python
# sessions collection
await sessions.create_index([("session_id", ASCENDING)], unique=True)
await sessions.create_index([("workflow_type", ASCENDING)])
await sessions.create_index([("entities.name", ASCENDING)])
await sessions.create_index([("end_time", ASCENDING)])
await sessions.create_index([("raw_transcript_expires_at", ASCENDING)], 
                           expireAfterSeconds=0)  # TTL index

# permanent_memory collection
await permanent_memory.create_index([("tags", ASCENDING)])
await permanent_memory.create_index([("memory_id", ASCENDING)], unique=True)

# entities collection
await entities.create_index([("name", ASCENDING), ("entity_type", ASCENDING)], 
                           unique=True)
```

#### Neo4j Indexes
```cypher
CREATE INDEX entity_name_project IF NOT EXISTS 
FOR (n:Project) ON (n.name);

CREATE INDEX entity_name_skill IF NOT EXISTS 
FOR (n:Skill) ON (n.name);

CREATE INDEX entity_name_person IF NOT EXISTS 
FOR (n:User) ON (n.name);

CREATE INDEX entity_name_interest IF NOT EXISTS 
FOR (n:Interest) ON (n.name);

CREATE INDEX entity_name_commitment IF NOT EXISTS 
FOR (n:Commitment) ON (n.name);

CREATE INDEX session_id IF NOT EXISTS 
FOR (n:Session) ON (n.session_id);
```

---

## Implementation Guide

### Step 1: Install Dependencies

```bash
# Core dependencies
pip install motor pymongo redis pinecone-client neo4j google-generativeai groq

# ML dependencies
pip install sentence-transformers summa

# Optional: for testing
pip install pytest pytest-asyncio
```

### Step 2: Environment Configuration

Create `.env` file:
```bash
# MongoDB
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
DB_NAME=asta_memory

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_TTL_HOT=3600
REDIS_TTL_ENTITY=86400

# Neo4j
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j

# Pinecone
PINECONE_API_KEY=your-key
PINECONE_INDEX_NAME=asta-memory-v2

# LLM & Embeddings
GROQ_API_KEY=your-key
GEMINI_API_KEY=your-key

# Memory Settings
MEMORY_TOP_K_SESSIONS=3
MEMORY_CLUSTER_DEPTH=2
SESSION_TRANSCRIPT_TTL_DAYS=90
```

### Step 3: Initialize Schema

```bash
# Initialize Neo4j schema (run once)
python -m memory.schema_init
```

### Step 4: Integrate with Your App

```python
from memory import memory_engine

# At app startup
async def startup():
    status = await memory_engine.connect_all()
    print(f"Memory layers: {status}")

# At session start
async def handle_new_session(session_id: str, user_input: str):
    context = await memory_engine.get_context_for_session(
        session_id=session_id,
        user_input=user_input,
        workflow_type="research"
    )
    
    formatted = memory_engine.format_context_for_prompt(context)
    
    # Inject into your LLM system prompt
    system_prompt = f"""You are ASTA.
    
{formatted}

Now respond to the user..."""

# During conversation
async def handle_user_message(session_id: str, message: str):
    # Trigger prefetch (non-blocking)
    await memory_engine.on_user_message(session_id, message)

# At session end
async def handle_session_end(session_id: str, messages: List[Dict]):
    success = await memory_engine.save_session(
        session_id=session_id,
        workflow_type="research",
        messages=messages,
        start_time="2026-04-21T10:00:00",
        notion_page_id=""
    )

# At app shutdown
async def shutdown():
    await memory_engine.disconnect_all()
```

### Step 5: File Structure

```
your_project/
├── memory/
│   ├── __init__.py
│   ├── memory_engine.py       # Master orchestrator
│   ├── l1_cache.py            # Redis layer
│   ├── l2_graph.py            # Neo4j layer
│   ├── l3_vectors.py          # Pinecone layer
│   ├── l4_store.py            # MongoDB layer
│   ├── memory_saga.py         # Atomic write coordinator
│   ├── entity_extractor.py    # Groq entity extraction
│   ├── prefetch_engine.py     # Speculative prefetch
│   ├── schema.py              # Data models
│   └── schema_init.py         # Neo4j initialization
├── backend/
│   ├── app/
│   │   ├── config.py          # Settings
│   │   ├── main.py            # FastAPI app
│   │   └── api/
│   │       └── ws_routes.py   # WebSocket routes
│   └── requirements.txt
└── .env
```

---

## Configuration

### Memory Layer Settings

```python
# backend/app/config.py

class Settings(BaseSettings):
    # Memory Layer
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_HOT: int = 3600          # 1 hour
    REDIS_TTL_PREFETCH: int = 1800     # 30 min
    REDIS_TTL_ENTITY: int = 86400      # 24 hours
    
    MEMORY_TOP_K_SESSIONS: int = 3     # Past sessions to inject
    MEMORY_CLUSTER_DEPTH: int = 2      # Neo4j traversal depth
    MEMORY_PREFETCH_ENABLED: bool = True
    
    SESSION_TRANSCRIPT_TTL_DAYS: int = 90
    
    # Database URIs
    MONGO_URI: str
    NEO4J_URI: str
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "asta-memory-v2"
    
    # LLM Keys
    GROQ_API_KEY: str
    GEMINI_API_KEY: str
```

### Tuning Parameters

#### Retrieval Performance
```python
# Increase for more context (slower)
MEMORY_TOP_K_SESSIONS = 5

# Increase for broader entity relationships (slower)
MEMORY_CLUSTER_DEPTH = 3

# Decrease for faster retrieval (less context)
MEMORY_TOP_K_SESSIONS = 2
MEMORY_CLUSTER_DEPTH = 1
```

#### Cache TTLs
```python
# Longer TTL = more cache hits, more memory usage
REDIS_TTL_HOT = 7200        # 2 hours
REDIS_TTL_ENTITY = 172800   # 48 hours

# Shorter TTL = fresher data, more database hits
REDIS_TTL_HOT = 1800        # 30 min
REDIS_TTL_ENTITY = 43200    # 12 hours
```

---

## API Reference

### MemoryEngine

#### `connect_all() -> Dict[str, str]`
Connect all memory layers. Call once at app startup.

**Returns**:
```python
{
    "L1_redis": "connected",
    "L2_neo4j": "connected",
    "L3_pinecone": "connected",
    "L4_mongodb": "connected",
    "prefetch_engine": "started"
}
```

#### `get_context_for_session(session_id, user_input, workflow_type) -> Dict`
Retrieve relevant past context for a new session.

**Args**:
- `session_id` (str): Unique session identifier
- `user_input` (str): User's first message
- `workflow_type` (str): "research", "routine", or "content"

**Returns**:
```python
{
    "sessions": [
        {
            "session_id": "...",
            "workflow_type": "research",
            "summary": "...",
            "entities": [...],
            "topics": [...],
            "end_time": "2026-04-21T10:00:00"
        }
    ],
    "from_cache": False,
    "entities_spotted": ["ASTA", "Redis"]
}
```

#### `save_session(session_id, workflow_type, messages, start_time, notion_page_id="") -> bool`
Save complete session at the end.

**Args**:
- `session_id` (str): Unique session identifier
- `workflow_type` (str): "research", "routine", or "content"
- `messages` (List[Dict]): Conversation messages
- `start_time` (str): ISO datetime when session started
- `notion_page_id` (str, optional): Notion page ID if created

**Returns**: `True` on success, `False` on failure

#### `remember(content, tags) -> Dict`
Save to permanent memory.

**Args**:
- `content` (str): What to remember
- `tags` (List[str]): Tags for categorization

**Returns**:
```python
{
    "memory_id": "uuid",
    "content": "...",
    "tags": ["tag1", "tag2"],
    "date_stored": "2026-04-21T10:00:00",
    "recalled_count": 0
}
```

#### `recall(query_text, top_k=5) -> List[Dict]`
Recall permanent memories by semantic search.

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
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: password
    volumes:
      - mongo_data:/data/db

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - MONGO_URI=mongodb://admin:password@mongodb:27017/
      - NEO4J_URI=${NEO4J_URI}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - PINECONE_API_KEY=${PINECONE_API_KEY}
      - GROQ_API_KEY=${GROQ_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    depends_on:
      - redis
      - mongodb

volumes:
  redis_data:
  mongo_data:
```

### Production Checklist

- [ ] Use managed Redis (AWS ElastiCache, Redis Cloud)
- [ ] Use MongoDB Atlas (auto-scaling, backups)
- [ ] Use Neo4j Aura (managed graph database)
- [ ] Use Pinecone serverless (auto-scaling)
- [ ] Set up monitoring (Datadog, New Relic)
- [ ] Configure log aggregation (CloudWatch, Elasticsearch)
- [ ] Set up alerts for failed saga retries
- [ ] Enable SSL/TLS for all connections
- [ ] Rotate API keys regularly
- [ ] Set up backup strategy for MongoDB
- [ ] Configure Neo4j backups
- [ ] Monitor Pinecone usage and costs
- [ ] Set up health check endpoints
- [ ] Configure auto-scaling for app servers

---

## Summary

This memory layer provides:

1. **Fast retrieval** (<200ms) via multi-tier caching
2. **Semantic search** with vector embeddings
3. **Entity relationships** via knowledge graph
4. **Atomic writes** with retry guarantees
5. **Speculative prefetching** for zero-latency context
6. **Automatic entity extraction** from conversations

To implement in your project:
1. Copy the `memory/` folder
2. Configure `.env` with your credentials
3. Run `python -m memory.schema_init`
4. Integrate with your app using `memory_engine`
5. Deploy with managed services for production

The architecture is designed to be **modular** - you can swap out any layer (e.g., use Qdrant instead of Pinecone) without affecting the others.
