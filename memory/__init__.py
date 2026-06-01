"""
ASTA Memory Layer
─────────────────
5-layer persistent memory system:
  L0  In-flight context (LangGraph state)
  L1  Redis hot cache (entities + session context)
  L1.5 Speculative prefetch (background entity loading)
  L2  Neo4j knowledge graph (entity clusters + relationships)
  L3  Pinecone vector store (semantic search)
  L4  MongoDB cold store (full sessions + permanent memory)

Usage:
  from memory import memory_engine
  await memory_engine.connect_all()             # on startup
  ctx = await memory_engine.get_context_for_session(session_id, input, wf)
  await memory_engine.on_user_message(session_id, message)
  await memory_engine.save_session(session_id, ...)  # on session end
"""

from memory.memory_engine import memory_engine
from memory.schema import SessionMetadata, Entity, MemoryContextSlice, ENTITY_TYPES

__all__ = ["memory_engine", "SessionMetadata", "Entity", "MemoryContextSlice", "ENTITY_TYPES"]