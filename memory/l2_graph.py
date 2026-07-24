"""
ASTA Memory Layer - L2 Knowledge Graph (Neo4j)
─────────────────────────────────────────────

This is the L2 knowledge graph layer using Neo4j Aura.
Manages entity relationships and cluster-based session retrieval.
"""

import asyncio
import logging
from typing import List, Dict, Optional
from neo4j import AsyncGraphDatabase, AsyncDriver
from backend.app.config import settings
from memory.schema import NEO4J_LABELS, NEO4J_RELATIONSHIPS

logger = logging.getLogger(__name__)

class L2Graph:
    """
    L2 knowledge graph layer using Neo4j Aura.
    
    Manages:
    - Entity nodes and relationships
    - Session-to-entity connections
    - Cluster-based retrieval for memory context
    """
    
    def __init__(self):
        self.driver: Optional[AsyncDriver] = None
        
    async def connect(self) -> None:
        """Connect to Neo4j and initialize root node and indexes."""
        try:
            # Create async driver
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
            )
            
            # Verify connection
            async with self.driver.session() as session:
                result = await session.run("RETURN 1")
                await result.consume()
            
            # Create root Karthik node
            await self._create_root_node()
            
            # Create indexes
            await self._create_indexes()
            
            logger.info("L2 Neo4j connected. Karthik root node ready.")
            
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    async def _create_root_node(self) -> None:
        """Create the root Karthik user node if it doesn't exist."""
        try:
            async with self.driver.session() as session:
                query = """
                MERGE (u:User {name: "Karthik"})
                ON CREATE SET u.created_at = datetime(), u.last_active_project = "", u.current_focus = ""
                RETURN u
                """
                await session.run(query)
                
        except Exception as e:
            logger.error(f"Failed to create root node: {e}")
    
    async def _create_indexes(self) -> None:
        """Create indexes for all entity types."""
        try:
            async with self.driver.session() as session:
                # Create indexes for each entity type
                for entity_type, label in NEO4J_LABELS.items():
                    if label != "User":  # Skip User, already handled
                        query = f"CREATE INDEX entity_name_{label.lower()} IF NOT EXISTS FOR (n:{label}) ON (n.name)"
                        await session.run(query)
                
                logger.info("L2 Neo4j indexes created")
                
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            # Don't raise - indexes might already exist
    
    async def upsert_entity(self, name: str, entity_type: str, description: str = "", relation: str = "HAS") -> None:
        """
        Create or update an entity node and link it to Karthik.
        
        Args:
            name: Entity name
            entity_type: One of ENTITY_TYPES (PROJECT, SKILL, etc.)
            description: Optional description
            relation: Relationship type (e.g. WORKING_ON)
        """
        try:
            # Get Neo4j label for entity type - validate against whitelist
            label = NEO4J_LABELS.get(entity_type.lower(), "Topic")
            
            # Security: Validate label is in allowed set
            if label not in NEO4J_LABELS.values():
                label = "Topic"  # Safe fallback
                
            clean_rel = "".join(c for c in relation.upper() if c.isalnum() or c == "_")
            if not clean_rel:
                clean_rel = "HAS"
            
            async with self.driver.session() as session:
                query = f"""
                MERGE (e:{label} {{name: $name}})
                ON CREATE SET e.created_at = datetime(), e.description = $desc
                ON MATCH SET e.last_seen = datetime()
                WITH e
                MATCH (u:User {{name: "Karthik"}})
                MERGE (u)-[:{clean_rel}]->(e)
                """
                
                await session.run(query, name=name, desc=description)
                
        except Exception as e:
            logger.error(f"Failed to upsert entity {name}: {e}")
    
    async def link_session_to_entities(self, session_id: str, entities: List, 
                                      workflow_type: str, summary_snippet: str) -> None:
        """
        Create session node and link it to all entities discussed.
        
        Args:
            session_id: Unique session identifier
            entities: List of Entity objects
            workflow_type: Type of workflow (research, routine, etc.)
            summary_snippet: First 200 chars of summary
        """
        try:
            async with self.driver.session() as session_tx:
                # First create the session node
                session_query = """
                MERGE (s:Session {session_id: $sid})
                ON CREATE SET s.workflow_type = $wt, s.summary = $summary, s.created_at = datetime()
                """
                
                await session_tx.run(
                    session_query, 
                    sid=session_id, 
                    wt=workflow_type, 
                    summary=summary_snippet
                )
                
                # Then link to each entity
                for entity in entities:
                    label = NEO4J_LABELS.get(entity.entity_type.lower(), "Topic")
                    
                    # Security: Validate label
                    if label not in NEO4J_LABELS.values():
                        label = "Topic"
                    
                    link_query = f"""
                    MATCH (e:{label} {{name: $name}})
                    MATCH (s:Session {{session_id: $sid}})
                    MERGE (s)-[:COVERS]->(e)
                    """
                    
                    await session_tx.run(link_query, name=entity.name, sid=session_id)
                
                logger.info(f"Session {session_id} linked to {len(entities)} entities")
                
        except Exception as e:
            logger.error(f"Failed to link session {session_id} to entities: {e}")
    
    async def get_cluster_session_ids(self, entity_names: List[str], depth: int = 2) -> List[str]:
        """
        Core retrieval query. Find all sessions that covered given entities
        OR entities related to them (up to depth hops).
        
        Args:
            entity_names: List of entity names to search for
            depth: How many relationship hops to traverse (default 2)
            
        Returns:
            List of session_id strings (capped at 50)
        """
        # Guard against None or empty input (before try block)
        if entity_names is None:
            raise TypeError("entity_names cannot be None")
        if not entity_names:
            return []
        
        try:
            async with self.driver.session() as session:
                # Query for direct matches and related entities
                query = f"""
                MATCH (u:User {{name: "Karthik"}})-[]->(e)
                WHERE e.name IN $names
                MATCH (s:Session)-[:COVERS]->(e)
                RETURN DISTINCT s.session_id as session_id
                UNION
                MATCH (u:User {{name: "Karthik"}})-[]->(e1)-[:RELATED_TO*1..{depth}]->(e2)
                WHERE e1.name IN $names
                MATCH (s:Session)-[:COVERS]->(e2)
                RETURN DISTINCT s.session_id as session_id
                LIMIT 50
                """
                
                result = await session.run(query, names=entity_names)
                records = await result.data()
                
                session_ids = [record["session_id"] for record in records]
                logger.info(f"Found {len(session_ids)} sessions for entities: {entity_names}")
                
                return session_ids
                
        except Exception as e:
            logger.error(f"Failed to get cluster session IDs: {e}")
            return []
    
    async def link_related_entities(self, entity_a: str, type_a: str, 
                                   entity_b: str, type_b: str) -> None:
        """
        Create a RELATED_TO relationship between two entities.
        
        Args:
            entity_a: First entity name
            type_a: First entity type
            entity_b: Second entity name  
            type_b: Second entity type
        """
        try:
            label_a = NEO4J_LABELS.get(type_a.lower(), "Topic")
            label_b = NEO4J_LABELS.get(type_b.lower(), "Topic")
            
            # Security: Validate labels
            if label_a not in NEO4J_LABELS.values():
                label_a = "Topic"
            if label_b not in NEO4J_LABELS.values():
                label_b = "Topic"
            
            async with self.driver.session() as session:
                query = f"""
                MERGE (a:{label_a} {{name: $name_a}})
                MERGE (b:{label_b} {{name: $name_b}})
                MERGE (a)-[:RELATED_TO]->(b)
                """
                
                await session.run(query, name_a=entity_a, name_b=entity_b)
                
        except Exception as e:
            logger.error(f"Failed to link entities {entity_a} -> {entity_b}: {e}")
    
    async def update_current_focus(self, project_or_topic: str) -> None:
        """Update Karthik's current focus in the User node."""
        try:
            async with self.driver.session() as session:
                query = """
                MATCH (u:User {name: "Karthik"})
                SET u.current_focus = $focus, u.last_active = datetime()
                """
                
                await session.run(query, focus=project_or_topic)
                
        except Exception as e:
            logger.error(f"Failed to update current focus: {e}")
    
    async def get_current_focus(self) -> Dict:
        """Get Karthik's current focus and activity info."""
        try:
            async with self.driver.session() as session:
                query = """
                MATCH (u:User {name: "Karthik"})
                RETURN u.current_focus as current_focus, 
                       u.last_active_project as last_active_project,
                       u.last_active as last_active
                """
                
                result = await session.run(query)
                record = await result.single()
                
                if record:
                    return {
                        "current_focus": record.get("current_focus", ""),
                        "last_active_project": record.get("last_active_project", ""),
                        "last_active": record.get("last_active", "")
                    }
                
                return {}
                
        except Exception as e:
            logger.error(f"Failed to get current focus: {e}")
            return {}
    
    async def get_all_entity_names(self) -> List[str]:
        """
        Get all entity names connected to Karthik.
        Used for real-time entity spotting in prefetch engine.
        """
        try:
            async with self.driver.session() as session:
                query = """
                MATCH (u:User {name: "Karthik"})-[]->(e)
                RETURN DISTINCT e.name as name
                """
                
                result = await session.run(query)
                records = await result.data()
                
                names = [record["name"] for record in records]
                return names
                
        except Exception as e:
            logger.error(f"Failed to get all entity names: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Check if Neo4j is actually reachable right now."""
        if not self.driver:
            return False
        try:
            async with self.driver.session() as session:
                result = await session.run("RETURN 1")
                await result.consume()
            return True
        except Exception:
            return False

    async def disconnect(self) -> None:
        """Close Neo4j driver connection."""
        if self.driver:
            await self.driver.close()

# Export singleton
l2_graph = L2Graph()