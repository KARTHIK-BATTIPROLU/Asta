import logging
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

from backend.app.config import settings

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

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

        neo4j_uri = getattr(settings, "NEO4J_URI", None)
        neo_user = getattr(settings, "NEO4J_USERNAME", None)
        neo_pass = getattr(settings, "NEO4J_PASSWORD", None)

        if not all([neo4j_uri, neo_user, neo_pass]):
            logger.warning("[GraphLTM] Neo4j Aura credentials missing. Skipping L2 Graph Init.")
            return

        try:
            # graphiti-core 0.29.x requires uri/user/password as constructor args --
            # it does not read NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD env vars itself.
            # It also defaults to OpenAI for LLM/embedding/reranking; this project
            # is Groq-first and doesn't carry a real OpenAI key, so wire Graphiti
            # to Gemini instead (already configured for this project). Groq was
            # tried for the LLM client first, but Graphiti's entity/edge
            # extraction prompt runs ~18-19k tokens per call, which exceeds this
            # account's free-tier TPM cap on EVERY Groq model available (12k on
            # llama-3.3-70b-versatile, 6k on llama-3.1-8b-instant) -- a platform
            # rate-limit ceiling, not something a different Groq model fixes.
            from graphiti_core.llm_client.gemini_client import GeminiClient
            from graphiti_core.llm_client.config import LLMConfig
            from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
            from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient

            llm_client = GeminiClient(config=LLMConfig(
                api_key=settings.GEMINI_API_KEY, model="gemini-2.5-flash",
            ))
            embedder = GeminiEmbedder(config=GeminiEmbedderConfig(
                api_key=settings.GEMINI_API_KEY, embedding_model="models/gemini-embedding-001",
            ))
            cross_encoder = GeminiRerankerClient(config=LLMConfig(api_key=settings.GEMINI_API_KEY))

            self.client = Graphiti(
                uri=neo4j_uri, user=neo_user, password=neo_pass,
                llm_client=llm_client, embedder=embedder, cross_encoder=cross_encoder,
            )

            # Register custom nodes (Graphiti extracts these automatically from text)
            # self.client.register_node_type(Priority)
            # self.client.register_node_type(Rule)
            # self.client.register_node_type(Contradiction)
            # self.client.register_node_type(Goal)
            # self.client.register_node_type(Project)
            # self.client.register_node_type(Person)
            # self.client.register_node_type(Idea)

            self.is_initialized = True
            logger.info("[GraphLTM] Graphiti initialized with Neo4j (Groq LLM + Gemini embedder/reranker).")
        except Exception as e:
            logger.error(f"[GraphLTM] Failed to initialize Graphiti: {e}")
            self.is_initialized = False

    async def add_episode(self, session_id: str, insights_text: str):
        """Pass insights as an 'episode' to Graphiti for edge extraction and temporal validity."""
        if not self.is_initialized or not self.client:
            return

        try:
            await self.client.add_episode(
                name=session_id,
                episode_body=insights_text,
                source_description="ASTA session extraction",
                reference_time=datetime.now(timezone.utc),
            )
            logger.info(f"[GraphLTM] Added episode {session_id} to Graphiti.")
        except Exception as e:
            logger.error(f"[GraphLTM] Failed to add episode: {e}")

    async def search(self, query: str, k: int = 12) -> List[Dict]:
        """Search Graphiti L2 knowledge graph for relevant context.

        graphiti-core 0.29.x's Graphiti.search() returns list[EntityEdge], not
        dicts, and takes num_results= rather than k=/center=. Normalize edges to
        the {"text": ...} shape recall() merges with the Mongo similarity pool.
        """
        if not self.is_initialized or not self.client:
            return []

        try:
            edges = await self.client.search(query, num_results=k)
            return [
                {"text": edge.fact, "ts": edge.valid_at or edge.created_at}
                for edge in edges
            ]
        except Exception as e:
            logger.error(f"[GraphLTM] Search failed: {e}")
            return []

graph_ltm = GraphLTMManager()
