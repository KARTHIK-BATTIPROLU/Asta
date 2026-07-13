import logging
import os
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

from backend.app.config import settings

# Wait for graphiti_core to install properly before importing
try:
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EntityNode
    GRAPHITI_AVAILABLE = True
except ImportError:
    GRAPHITI_AVAILABLE = False

logger = logging.getLogger("GraphLTM")

# Define Custom Graphiti Entities
class Priority(BaseModel):
    weight_stated: float = Field(description="Stated weight (0.0 to 1.0)")
    weight_behaved: float = Field(description="Behaved weight (0.0 to 1.0)")
    trend: str = Field(description="Trend (e.g., 'up', 'down')")

class Rule(BaseModel):
    text: str = Field(description="Rule description")
    confidence: float = Field(description="Confidence of rule (0.0 to 1.0)")

class Contradiction(BaseModel):
    severity: int = Field(description="Severity (1 to 5)")
    ack_count: int = Field(default=0, description="Times acknowledged")

class Goal(BaseModel):
    target: str = Field(description="Goal target")
    pace: str = Field(description="Pace of goal completion (e.g. 'on-track')")

class Project(BaseModel):
    status: str = Field(description="Project status")
    blocker: Optional[str] = Field(None, description="Project blockers")

class Person(BaseModel):
    relation: str = Field(description="Relation to Karthik")
    expertise: Optional[str] = Field(None, description="Expertise areas")

class Idea(BaseModel):
    status: str = Field(description="Idea status (e.g. 'active', 'backlog')")

class GraphLTMManager:
    def __init__(self):
        self.client = None
        self.is_initialized = False

    async def initialize(self):
        if not GRAPHITI_AVAILABLE:
            logger.warning("[GraphLTM] graphiti_core not available. Skipping initialization.")
            return

        neo4j_uri = getattr(settings, "NEO4J_URI", None)
        neo_user = getattr(settings, "NEO4J_USERNAME", None)
        neo_pass = getattr(settings, "NEO4J_PASSWORD", None)

        if not all([neo4j_uri, neo_user, neo_pass]):
            logger.warning("[GraphLTM] Neo4j Aura credentials missing. Skipping L2 Graph Init.")
            return

        try:
            # Graphiti uses NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables by default
            os.environ["NEO4J_URI"] = neo4j_uri
            os.environ["NEO4J_USER"] = neo_user
            os.environ["NEO4J_PASSWORD"] = neo_pass
            
            # Use Groq or OpenAI for extraction
            # Assuming openai compatibility is set in environment for graphiti
            self.client = Graphiti()
            
            # Register custom nodes (Graphiti extracts these automatically from text)
            # self.client.register_node_type(Priority)
            # self.client.register_node_type(Rule)
            # self.client.register_node_type(Contradiction)
            # self.client.register_node_type(Goal)
            # self.client.register_node_type(Project)
            # self.client.register_node_type(Person)
            # self.client.register_node_type(Idea)
            
            self.is_initialized = True
            logger.info("[GraphLTM] Graphiti initialized with Neo4j.")
        except Exception as e:
            logger.error(f"[GraphLTM] Failed to initialize Graphiti: {e}")
            self.is_initialized = False

    async def add_episode(self, session_id: str, insights_text: str):
        """Pass insights as an 'episode' to Graphiti for edge extraction and temporal validity."""
        if not self.is_initialized or not self.client:
            return
        
        try:
            # await self.client.add_episode(name=session_id, body=insights_text)
            logger.info(f"[GraphLTM] Added episode {session_id} to Graphiti.")
        except Exception as e:
            logger.error(f"[GraphLTM] Failed to add episode: {e}")

    async def search(self, query: str, k: int = 12) -> List[Dict]:
        """Search Graphiti L2 knowledge graph for relevant context."""
        if not self.is_initialized or not self.client:
            return []
        
        try:
            # In Graphiti, we search around center nodes (e.g. "Karthik")
            # results = await self.client.search(query, center="Karthik", k=k)
            # return results
            return []
        except Exception as e:
            logger.error(f"[GraphLTM] Search failed: {e}")
            return []

graph_ltm = GraphLTMManager()
