# Memory Layer Visual Guide

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    ASTA MEMORY ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  L0: In-Flight Context (LangGraph State)                        │
│  ├─ Current conversation turn                                   │
│  └─ System prompt + user message                                │
│                                                                  │
│  L1: Hot Cache (Redis) - 1 hour TTL                            │
│  ├─ Active sessions                                             │
│  ├─ Entity context cache                                        │
│  └─ Retrieved context cache                                     │
│                                                                  │
│  L1.5: Speculative Prefetch (Background Queue)                 │
│  ├─ Triggered by partial STT transcripts                       │
│  └─ Pre-loads entity context into L1                           │
│                                                                  │
│  L2: Knowledge Graph (Neo4j Aura)                              │
│  ├─ Entity nodes (Projects, Skills, People, etc.)             │
│  ├─ Session nodes                                               │
│  └─ Relationships (COVERS, RELATED_TO, etc.)                   │
│                                                                  │
│  L3: Vector Store (Pinecone Serverless)                        │
│  ├─ Session summary embeddings (3072-dim)                      │
│  ├─ Semantic search                                             │
│  └─ Filtered by Neo4j clusters                                 │
│                                                                  │
│  L4: Cold Store (MongoDB Atlas)                                │
│  ├─ Full session documents                                      │
│  ├─ Raw transcripts (90-day TTL)                               │
│  ├─ Permanent memory                                            │
│  └─ Entity registry                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Write Flow (Session End)

```
┌──────────────────┐
│  Session Ends    │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Extract Entities & Generate Summary │
│  ├─ Groq llama-3.3-70b (entities)   │
│  ├─ TextRank (summary)               │
│  └─ Google gemini (embedding)        │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│       Memory Saga (Atomic Write)     │
├──────────────────────────────────────┤
│                                      │
│  Phase 1: MongoDB ✓ (REQUIRED)      │
│  ┌────────────────────────────────┐ │
│  │ • Full session document        │ │
│  │ • embedding_status: pending    │ │
│  │ • neo4j_status: pending        │ │
│  └────────────────────────────────┘ │
│           │                          │
│           ▼                          │
│  Phase 2: Pinecone (retry on fail)  │
│  ┌────────────────────────────────┐ │
│  │ • Upsert vector                │ │
│  │ • Update embedding_status      │ │
│  └────────────────────────────────┘ │
│           │                          │
│           ▼                          │
│  Phase 3: Neo4j (retry on fail)     │
│  ┌────────────────────────────────┐ │
│  │ • Create Session node          │ │
│  │ • Link to entities             │ │
│  │ • Create HIGH confidence nodes │ │
│  │ • Store MEDIUM/LOW for approval│ │
│  └────────────────────────────────┘ │
│                                      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Cleanup & Refresh                   │
│  ├─ Invalidate L1 cache              │
│  ├─ Refresh prefetch engine          │
│  └─ Update entity cache              │
└──────────────────────────────────────┘
```

## Read Flow (Session Start)

```
┌──────────────────┐
│  User Query      │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Check L1 Retrieved Context Cache    │
└────────┬─────────────────────────────┘
         │
    ┌────┴────┐
    │  HIT?   │
    └────┬────┘
         │
    ┌────┴────┐
    │   YES   │───────────────────────┐
    └─────────┘                       │
         │                            │
    ┌────┴────┐                       │
    │   NO    │                       │
    └────┬────┘                       │
         │                            │
         ▼                            │
┌──────────────────────────────────┐  │
│  Entity Spotting                 │  │
│  ├─ Regex match known entities   │  │
│  └─ Check Neo4j current_focus    │  │
└────────┬─────────────────────────┘  │
         │                            │
         ▼                            │
┌──────────────────────────────────┐  │
│  Check L1 Entity Context Cache   │  │
└────────┬─────────────────────────┘  │
         │                            │
    ┌────┴────┐                       │
    │  HIT?   │                       │
    └────┬────┘                       │
         │                            │
    ┌────┴────┐                       │
    │   YES   │───────────────────┐   │
    └─────────┘                   │   │
         │                        │   │
    ┌────┴────┐                   │   │
    │   NO    │                   │   │
    └────┬────┘                   │   │
         │                        │   │
         ▼                        │   │
┌──────────────────────────────┐  │   │
│  Parallel Retrieval          │  │   │
│  (1.5s timeout)              │  │   │
├──────────────────────────────┤  │   │
│                              │  │   │
│  Thread 1: Neo4j             │  │   │
│  ┌────────────────────────┐ │  │   │
│  │ Get cluster session_ids│ │  │   │
│  └────────────────────────┘ │  │   │
│           │                  │  │   │
│           ▼                  │  │   │
│  Thread 2: Pinecone          │  │   │
│  ┌────────────────────────┐ │  │   │
│  │ Embed query            │ │  │   │
│  │ Filter by cluster_ids  │ │  │   │
│  │ Get top-K vectors      │ │  │   │
│  └────────────────────────┘ │  │   │
│                              │  │   │
└────────┬─────────────────────┘  │   │
         │                        │   │
         ▼                        │   │
┌──────────────────────────────┐  │   │
│  Late Fusion (RRF)           │  │   │
│  ├─ Merge results            │  │   │
│  └─ Rank by relevance        │  │   │
└────────┬─────────────────────┘  │   │
         │                        │   │
         ▼                        │   │
┌──────────────────────────────┐  │   │
│  MongoDB Fetch Full Sessions │  │   │
└────────┬─────────────────────┘  │   │
         │                        │   │
         ▼                        │   │
┌──────────────────────────────┐  │   │
│  Format as Structured XML    │  │   │
└────────┬─────────────────────┘  │   │
         │                        │   │
         ▼                        │   │
┌──────────────────────────────┐  │   │
│  Cache in L1 for Session     │  │   │
└────────┬─────────────────────┘  │   │
         │                        │   │
         └────────────────────────┴───┘
         │
         ▼
┌──────────────────────────────────────┐
│  Return Context to LLM               │
└──────────────────────────────────────┘
```

## Speculative Prefetch Flow

```
┌──────────────────────────────┐
│  Partial STT Transcript      │
│  "Tell me about the ASTA..." │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  Intent Classification       │
│  (fast regex)                │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  Entity Spotting             │
│  Found: ["ASTA"]             │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  Add to Background Queue     │
│  (non-blocking)              │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Background Worker                   │
├──────────────────────────────────────┤
│                                      │
│  1. Neo4j cluster search             │
│     └─ Get sessions about "ASTA"     │
│                                      │
│  2. Pinecone vector search           │
│     └─ Semantic search for "ASTA"    │
│                                      │
│  3. MongoDB fetch                    │
│     └─ Get full session docs         │
│                                      │
│  4. Cache in L1                      │
│     └─ entity_ctx:asta               │
│                                      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  User Finishes Speaking              │
│  "Tell me about the ASTA project"    │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Retrieval Hits L1 Cache             │
│  ├─ entity_ctx:asta (CACHED)         │
│  └─ Return instantly (0ms)           │
└──────────────────────────────────────┘
```

## Neo4j Graph Structure

```
                    ┌─────────────────┐
                    │  User: KARTHIK  │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │      HAS        │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   Projects    │    │    Skills     │    │    People     │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
   ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
   │ CONTAINS│          │ CONTAINS│          │ CONTAINS│
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Project: ASTA │    │ Skill: Python │    │ Person: Ravi  │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────┴────────┐
                    │     COVERS      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Session Node   │
                    ├─────────────────┤
                    │ session_id      │
                    │ timestamp       │
                    │ summary         │
                    │ topics          │
                    └─────────────────┘
```

## Entity Extraction Flow

```
┌──────────────────────────────┐
│  Conversation Messages       │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Groq llama-3.3-70b-versatile        │
│  (Entity Extraction)                 │
├──────────────────────────────────────┤
│                                      │
│  Input: Full conversation            │
│  Output: Structured JSON             │
│                                      │
│  {                                   │
│    "session_properties": {           │
│      "topics": [...],                │
│      "tool_calls": [...]             │
│    },                                │
│    "relationships": {                │
│      "touches_projects": [...],      │
│      "uses_skills": [...],           │
│      "involves_people": [...]        │
│    },                                │
│    "new_nodes_to_create": {          │
│      "projects": [...],              │
│      "skills": [...]                 │
│    }                                 │
│  }                                   │
│                                      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Confidence Filtering                │
├──────────────────────────────────────┤
│                                      │
│  HIGH confidence                     │
│  └─ Create immediately in Neo4j      │
│                                      │
│  MEDIUM/LOW confidence               │
│  └─ Store in pending_confirmations   │
│                                      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Neo4j Graph Update                  │
│  ├─ Create new entity nodes          │
│  ├─ Create relationships             │
│  └─ Link session to entities         │
└──────────────────────────────────────┘
```

## Retry Worker Flow

```
┌──────────────────────────────┐
│  Saga Retry Worker           │
│  (Background Process)        │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  Poll every 30 seconds       │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Query MongoDB for Failed Sessions   │
│  WHERE:                              │
│    embedding_status = "pending" OR   │
│    neo4j_status = "pending"          │
└────────┬─────────────────────────────┘
         │
    ┌────┴────┐
    │ Found?  │
    └────┬────┘
         │
    ┌────┴────┐
    │   YES   │
    └────┬────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Retry Failed Operations             │
│  ├─ Pinecone upsert (if pending)     │
│  └─ Neo4j write (if pending)         │
└────────┬─────────────────────────────┘
         │
    ┌────┴────┐
    │ Success?│
    └────┬────┘
         │
    ┌────┴────┐
    │   YES   │───────────────────────┐
    └─────────┘                       │
         │                            │
    ┌────┴────┐                       │
    │   NO    │                       │
    └────┬────┘                       │
         │                            │
         ▼                            │
┌──────────────────────────────┐      │
│  Exponential Backoff         │      │
│  ├─ Attempt 1: 30s           │      │
│  ├─ Attempt 2: 60s           │      │
│  ├─ Attempt 3: 120s          │      │
│  └─ After 3: Dead Letter     │      │
└──────────────────────────────┘      │
                                      │
         ┌────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Update MongoDB Status               │
│  ├─ embedding_status: "complete"     │
│  └─ neo4j_status: "complete"         │
└──────────────────────────────────────┘
```

## Performance Metrics

```
┌─────────────────────────────────────────────────────────┐
│                  PERFORMANCE TARGETS                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Retrieval Latency:                                     │
│  ├─ L1 Cache Hit:        0-5ms                          │
│  ├─ L1 Entity Hit:       10-50ms                        │
│  ├─ Full Pipeline:       150-200ms (local)              │
│  └─ Cross-Region:        300-500ms                      │
│                                                          │
│  Write Latency:                                         │
│  ├─ MongoDB:             50-100ms                       │
│  ├─ Pinecone:            100-200ms                      │
│  ├─ Neo4j:               100-300ms                      │
│  └─ Total Saga:          250-600ms (async)              │
│                                                          │
│  Cache Hit Rates:                                       │
│  ├─ L1 Session:          >80%                           │
│  ├─ L1 Entity:           >60%                           │
│  └─ Prefetch Success:    >70%                           │
│                                                          │
│  Throughput:                                            │
│  ├─ Concurrent Sessions: 100+                           │
│  ├─ Writes/sec:          50+                            │
│  └─ Reads/sec:           500+                           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Data Size Estimates

```
┌─────────────────────────────────────────────────────────┐
│                    DATA SIZING                           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  L1 Redis:                                              │
│  ├─ Active Sessions:     ~100 × 10KB = 1MB             │
│  ├─ Entity Context:      ~1000 × 50KB = 50MB           │
│  └─ Total:               ~50-100MB                      │
│                                                          │
│  L2 Neo4j:                                              │
│  ├─ Entity Nodes:        ~10K × 1KB = 10MB             │
│  ├─ Session Nodes:       ~100K × 500B = 50MB           │
│  ├─ Relationships:       ~50K × 200B = 10MB            │
│  └─ Total:               ~70MB                          │
│                                                          │
│  L3 Pinecone:                                           │
│  ├─ Vectors:             ~100K × 12KB = 1.2GB          │
│  └─ Metadata:            ~100K × 1KB = 100MB           │
│  └─ Total:               ~1.3GB                         │
│                                                          │
│  L4 MongoDB:                                            │
│  ├─ Sessions:            ~100K × 50KB = 5GB            │
│  ├─ Transcripts:         ~100K × 200KB = 20GB          │
│  ├─ Permanent Memory:    ~1K × 10KB = 10MB             │
│  └─ Total:               ~25GB                          │
│                                                          │
│  Grand Total:            ~26.5GB                        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Summary

This visual guide shows:

1. **5-layer architecture** with clear separation of concerns
2. **Write flow** with atomic saga pattern
3. **Read flow** with parallel retrieval and late fusion
4. **Speculative prefetch** for zero-latency context
5. **Neo4j graph structure** for entity relationships
6. **Entity extraction** with confidence filtering
7. **Retry worker** for fault tolerance
8. **Performance targets** and data sizing

The architecture is designed for:
- **Speed**: <200ms retrieval with multi-tier caching
- **Reliability**: Atomic writes with retry guarantees
- **Scalability**: Horizontal scaling at each layer
- **Flexibility**: Modular design allows layer swapping
