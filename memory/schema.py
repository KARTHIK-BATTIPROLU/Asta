"""
ASTA Memory Layer Schema Definitions
───────────────────────────────────

This file defines ALL data structures used across the memory system.
Single source of truth for all memory data structures.
"""

from dataclasses import dataclass, field
from typing import Optional, TypedDict
from datetime import datetime

# ─── Entity Types ────────────────────────────────────────────────────────────

ENTITY_TYPES = ["PROJECT", "SKILL", "PERSON", "GOAL", "TOPIC", "DECISION", "TASK"]

@dataclass
class Entity:
    name: str
    entity_type: str          # one of ENTITY_TYPES
    description: str = ""
    confidence: float = 1.0   # 0.0–1.0, from LLM extraction

@dataclass  
class SessionMetadata:
    session_id: str
    workflow_type: str
    start_time: str           # ISO datetime string
    end_time: str
    summary: str              # 3-5 bullet point summary
    entities: list            # list of Entity objects
    topics: list              # simple list of topic strings
    embedding_id: str = ""    # Pinecone vector ID
    notion_page_id: str = ""

# ─── Cache Payloads ──────────────────────────────────────────────────────────

@dataclass
class CachedContext:
    entity_name: str
    entity_type: str
    related_sessions: list    # list of SessionMetadata dicts
    last_updated: str         # ISO datetime
    hit_count: int = 0

@dataclass
class ActiveSession:
    session_id: str
    workflow_type: str
    start_time: str
    messages_count: int = 0
    entities_seen: list = field(default_factory=list)  # entities spotted so far

# ─── LangGraph State Memory Slice ────────────────────────────────────────────

class MemoryContextSlice(TypedDict):
    retrieved_sessions: list         # top-K past sessions as dicts
    active_entities: list            # entities seen in current session
    prefetched_context: dict         # keyed by entity_name → CachedContext dict
    session_metadata: dict           # current session's SessionMetadata dict

# ─── Neo4j Node/Rel labels (constants) ───────────────────────────────────────

NEO4J_LABELS = {
    "root": "User",
    "project": "Project",
    "skill": "Skill",
    "person": "Person",
    "goal": "Goal",
    "topic": "Topic",
    "decision": "Decision",
    "task": "Task",
    "session": "Session",
}

NEO4J_RELATIONSHIPS = {
    "has_entity": "HAS",             # User → any entity
    "session_covers": "COVERS",     # Session → any entity
    "related_to": "RELATED_TO",     # entity → entity
    "led_to": "LED_TO",             # Session → Decision/Task
}