"""
Neo4j Graph Service for ASTA Memory Layer
Implements exact schema from ASTA specification with PERSISTENT CONNECTION
"""
import logging
import os
from typing import List, Dict, Any, Optional
from neo4j import AsyncGraphDatabase
from datetime import datetime

logger = logging.getLogger("GraphService")

# PERSISTENT Neo4j driver - created ONCE at module level
_driver = None

def _get_driver():
    """Get or create persistent Neo4j driver (singleton pattern)"""
    global _driver
    if _driver is None:
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USERNAME")
        neo4j_pass = os.getenv("NEO4J_PASSWORD")
        
        if not all([neo4j_uri, neo4j_user, neo4j_pass]):
            raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD required")
        
        _driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_pass),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=2.0
        )
        logger.info("Neo4j persistent driver created")
    
    return _driver


class GraphService:
    """
    Neo4j service with PERSISTENT connection pool.
    Driver is created once and reused for all queries.
    """
    
    def __init__(self):
        self.driver = _get_driver()
    
    async def create_session_node(
        self,
        session_id: str,
        timestamp: str,
        ended_at: str,
        duration_seconds: int,
        summary: str,
        topics: List[str],
        tool_calls: List[str],
        message_count: int,
        pending_confirmations: List[str]
    ) -> bool:
        """
        Create Session node and link to KARTHIK Person node.
        Uses persistent driver - NO reconnection overhead.
        """
        try:
            query = """
            MERGE (p:Person {name: "Karthik"})
            MERGE (s:Session {session_id: $session_id})
            SET s.timestamp = datetime($timestamp),
                s.ended_at = datetime($ended_at),
                s.duration_seconds = $duration_seconds,
                s.summary = $summary,
                s.topics = $topics,
                s.tool_calls = $tool_calls,
                s.message_count = $message_count,
                s.pending_confirmations = $pending_confirmations
            MERGE (s)-[:RELATED_TO]->(p)
            RETURN s.session_id as session_id
            """
            
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    session_id=session_id,
                    timestamp=timestamp,
                    ended_at=ended_at,
                    duration_seconds=duration_seconds,
                    summary=summary,
                    topics=topics,
                    tool_calls=tool_calls,
                    message_count=message_count,
                    pending_confirmations=[str(pc) for pc in pending_confirmations]
                )
                record = await result.single()
                
            logger.info(f"Created Session node: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create Session node: {e}")
            raise  # Must propagate - this is critical
    
    async def link_session_to_node(
        self,
        session_id: str,
        relationship_type: str,
        target_name: str,
        target_label: str
    ) -> bool:
        """
        Create typed relationship between Session and target node.
        Uses persistent driver - NO reconnection overhead.
        """
        try:
            query = f"""
            MATCH (s:Session {{session_id: $session_id}})
            MATCH (t:{target_label} {{name: $target_name}})
            MERGE (s)-[:{relationship_type}]->(t)
            """
            
            async with self.driver.session() as session:
                await session.run(
                    query,
                    session_id=session_id,
                    target_name=target_name
                )
            
            logger.info(f"Created edge: Session({session_id}) -[:{relationship_type}]-> {target_label}({target_name})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create typed edge: {e}")
            return False
    
    async def create_typed_edge(
        self,
        session_id: str,
        relationship_type: str,
        target_name: str,
        target_label: str
    ) -> bool:
        """
        Alias for link_session_to_node for backward compatibility.
        """
        return await self.link_session_to_node(
            session_id, relationship_type, target_name, target_label
        )
    
    async def create_dynamic_node(
        self,
        node_type: str,
        node_data: Dict[str, Any],
        parent_category: str
    ) -> bool:
        """
        Create a new dynamic node.
        Uses persistent driver - NO reconnection overhead.
        """
        try:
            label_map = {
                "project": "Project",
                "skill": "Skill",
                "tool": "Tool",
                "person": "User",
                "interest": "Category",
                "commitment": "Commitment"
            }
            
            label = label_map.get(node_type, "Project")
            name = node_data.get("name") or node_data.get("description", "Unknown")
            
            # Create node and link to category
            if node_type == "skill":
                query = """
                MATCH (c:Category {name: $category})
                MATCH (sg:SkillGroup {name: $skill_group})
                MERGE (n:Skill {name: $name})
                SET n += $properties
                MERGE (sg)-[:CONTAINS]->(n)
                """
                
                async with self.driver.session() as session:
                    await session.run(
                        query,
                        category=parent_category,
                        skill_group=node_data.get("skill_group", "Programming Languages"),
                        name=name,
                        properties=node_data
                    )
            else:
                query = f"""
                MATCH (c:Category {{name: $category}})
                MERGE (n:{label} {{name: $name}})
                SET n += $properties
                MERGE (c)-[:CONTAINS]->(n)
                """
                
                async with self.driver.session() as session:
                    await session.run(
                        query,
                        category=parent_category,
                        name=name,
                        properties=node_data
                    )
            
            logger.info(f"Created dynamic node: {label}({name})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create dynamic node: {e}")
            return False
    
    async def get_existing_nodes(self) -> Optional[Dict[str, List[str]]]:
        """
        Get all existing nodes for entity extraction context.
        Uses persistent driver - NO reconnection overhead.

        Returns None (not {}) on connection failure, so callers can
        distinguish "Neo4j unreachable" from "connected but empty graph".
        """
        try:
            query = """
            MATCH (n)
            WHERE n:Project OR n:Skill OR n:Tool OR n:User OR n:Category OR n:Commitment
            RETURN labels(n)[0] as label, n.name as name
            """

            async with self.driver.session() as session:
                result = await session.run(query)
                records = await result.data()

            nodes_by_type = {}
            for record in records:
                label = record["label"]
                name = record["name"]

                if label not in nodes_by_type:
                    nodes_by_type[label] = []
                nodes_by_type[label].append(name)

            return nodes_by_type

        except Exception as e:
            logger.error(f"Failed to get existing nodes: {e}")
            return None
    
    async def search_graph_context(
        self,
        query: str,
        limit: int = 50
    ) -> List[str]:
        """
        Search graph for relevant session IDs.
        Uses persistent driver - NO reconnection overhead.
        """
        try:
            cypher_query = """
            MATCH (s:Session)-[r]->(n)
            WHERE toLower(n.name) CONTAINS toLower($search_query)
            OR ANY(topic IN s.topics WHERE toLower(topic) CONTAINS toLower($search_query))
            RETURN DISTINCT s.session_id as session_id
            LIMIT $limit
            """
            
            async with self.driver.session() as session:
                result = await session.run(
                    cypher_query,
                    search_query=query,
                    limit=limit
                )
                records = await result.data()
            
            session_ids = [r["session_id"] for r in records if r.get("session_id")]
            logger.info(f"Graph search found {len(session_ids)} sessions for query: {query}")
            return session_ids
            
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []


    async def initialize_base_graph(self) -> bool:
        """
        Initialize base Neo4j graph structure with constraints and indexes.
        Creates the foundational schema for ASTA's knowledge graph.
        """
        try:
            queries = [
                # Create constraints for unique identifiers
                "CREATE CONSTRAINT session_id_unique IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE",
                "CREATE CONSTRAINT person_name_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
                "CREATE CONSTRAINT project_name_unique IF NOT EXISTS FOR (pr:Project) REQUIRE pr.name IS UNIQUE",
                "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS FOR (sk:Skill) REQUIRE sk.name IS UNIQUE",
                "CREATE CONSTRAINT tool_name_unique IF NOT EXISTS FOR (t:Tool) REQUIRE t.name IS UNIQUE",
                
                # Create indexes for performance
                "CREATE INDEX session_timestamp_idx IF NOT EXISTS FOR (s:Session) ON (s.timestamp)",
                "CREATE INDEX person_name_idx IF NOT EXISTS FOR (p:Person) ON (p.name)",
                
                # Create base category structure
                """
                MERGE (projects:Category {name: "Projects"})
                MERGE (skills:Category {name: "Skills"})
                MERGE (tools:Category {name: "Tools"})
                MERGE (people:Category {name: "People"})
                MERGE (interests:Category {name: "Interests"})
                MERGE (commitments:Category {name: "Commitments"})
                """,
                
                # Create skill groups under Skills category
                """
                MATCH (skills:Category {name: "Skills"})
                MERGE (prog_langs:SkillGroup {name: "Programming Languages"})
                MERGE (frameworks:SkillGroup {name: "Frameworks"})
                MERGE (databases:SkillGroup {name: "Databases"})
                MERGE (cloud:SkillGroup {name: "Cloud Services"})
                MERGE (skills)-[:CONTAINS]->(prog_langs)
                MERGE (skills)-[:CONTAINS]->(frameworks)
                MERGE (skills)-[:CONTAINS]->(databases)
                MERGE (skills)-[:CONTAINS]->(cloud)
                """,
                
                # Create Karthik person node (central user)
                """
                MERGE (karthik:Person {name: "Karthik"})
                SET karthik.role = "User",
                    karthik.created_at = datetime()
                """,
                
                # Create some initial projects
                """
                MATCH (projects:Category {name: "Projects"})
                MERGE (asta:Project {name: "ASTA"})
                SET asta.description = "AI Voice Assistant with Memory Layer",
                    asta.status = "active",
                    asta.created_at = datetime()
                MERGE (projects)-[:CONTAINS]->(asta)
                """,
                
                # Create some initial tools
                """
                MATCH (tools:Category {name: "Tools"})
                MERGE (notion:Tool {name: "Notion"})
                MERGE (search:Tool {name: "Search"})
                MERGE (weather:Tool {name: "Weather"})
                MERGE (calendar:Tool {name: "Calendar"})
                MERGE (tools)-[:CONTAINS]->(notion)
                MERGE (tools)-[:CONTAINS]->(search)
                MERGE (tools)-[:CONTAINS]->(weather)
                MERGE (tools)-[:CONTAINS]->(calendar)
                """
            ]
            
            async with self.driver.session() as session:
                for query in queries:
                    await session.run(query)
            
            logger.info("Neo4j base graph structure initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize base graph structure: {e}")
            return False


# Global instance with persistent connection
graph_service = GraphService()