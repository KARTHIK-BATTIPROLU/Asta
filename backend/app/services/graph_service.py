import logging
import asyncio
import json
from datetime import datetime, timezone
from neo4j import AsyncGraphDatabase
from backend.app.db.database import db_manager
from backend.app.config import config
from groq import AsyncGroq

logger = logging.getLogger("L3_Graph")

groq_client = AsyncGroq(api_key=config.GROQ_API_KEY)


class L3GraphManager:
    """
    Deterministic Neo4j graph layer.
    Solar System Architecture Schema:
        (u:User {name: "KARTHIK"})-[:HAS_CATEGORY]->(:Category {name: "PROJECTS"})
        (u:User {name: "KARTHIK"})-[:HAS_CATEGORY]->(:Category {name: "SKILLS"})
        (u:User {name: "KARTHIK"})-[:HAS_PROPERTY]->(p:Property)
        (s:Session)-[:MENTIONED_IN]->(p:Property)
        (p:Property)-[:BELONGS_TO]->(:Category)
    """

    @property
    def driver(self):
        return db_manager.neo4j_driver

    # ── Startup: Base Graph ─────────────────────────────────────────────
    async def initialize_base_graph(self, user_name: str = "KARTHIK"):
        """Creates the root User node and Category hubs. Safe to re-run (MERGE)."""
        if not self.driver:
            logger.warning("[GRAPH] Neo4j driver unavailable — skipping base graph init.")
            return

        query = """
        MERGE (u:User {name: $user_name})
        MERGE (skills:Category {name: "SKILLS"})
        MERGE (projects:Category {name: "PROJECTS"})
        MERGE (u)-[:HAS_CATEGORY]->(skills)
        MERGE (u)-[:HAS_CATEGORY]->(projects)
        """
        try:
            async with self.driver.session() as session:
                await session.run(query, user_name=user_name)
            logger.info(f"[GRAPH] Base graph initialized for {user_name}.")
        except Exception as e:
            logger.error(f"[GRAPH] Base graph init failed: {e}")

    # ── Entity Extraction via LLM ───────────────────────────────────────
    async def _extract_entities(self, summary_text: str, known_properties: list[str]) -> dict:
        """
        Uses Groq JSON mode to extract projects and skills from summary text.
        State-aware LLM property extraction using known properties.
        """
        try:
            prompt = f"""ROLE: You are the Neural Architect for KARTHIK's memory.

CONTEXT: You are processing a summary of a recent voice session.

GOAL: Extract or create "Property" nodes (Projects or Skills) and link the current Session to them.

RULES:
- User Root: Everything belongs to the user node KARTHIK.
- Property Extraction: Identify if the user is talking about a PROJECT or a SKILL.
- STRICT Deduplication: You MUST map the mentioned projects/skills to the EXACT names in the 'KNOWN PROPERTIES' list if they are conceptually the same.
  - DO NOT create variations like "ASTA Backend" if "ASTA" already exists. State-aware mapping is critical.
  - If a property already exists conceptually in the provided list, DO NOT create a new node. Map it to the existing name inside `existing_properties`.
- Edge Creation:
    - Create a :Property node if it's genuinely new.
    - Link (KARTHIK)-[:HAS_PROPERTY]->(Property).
    - Link (Session)-[:MENTIONED_IN]->(Property).

KNOWN PROPERTIES: {known_properties}

OUTPUT FORMAT (JSON ONLY):
{{
  "new_properties": [{{"type": "PROJECT" | "SKILL", "name": "..."}}],
  "existing_properties": ["..."]
}}

Text: {summary_text}"""

            response = await groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",  # Used smaller model for background task to save rate limit
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            data = json.loads(response.choices[0].message.content)
            result = {
                "new_properties": data.get("new_properties", []),
                "existing_properties": data.get("existing_properties", [])
            }
            logger.info(f"[GRAPH] Extracted {len(result['new_properties'])} new, {len(result['existing_properties'])} existing properties.")
            return result
        except Exception as e:
            logger.error(f"[GRAPH] Entity extraction failed: {e}")
            return {"new_properties": [], "existing_properties": []}

    # ── Graph Update Pipeline ───────────────────────────────────────────
    async def update_graph_knowledge(
        self, session_id: str, summary_ref: str, user_name: str = "KARTHIK"
    ):
        """
        Full graph update pipeline for Solar System model.
        1. Pre-fetch existing Properties
        2. Extract entities via LLM
        3. MERGE Session node
        4. MERGE Property nodes + relationships
        Runs as fire-and-forget task.
        """
        if not self.driver:
            logger.warning("[GRAPH] Neo4j driver unavailable — skipping graph update.")
            return

        date_iso = datetime.now(timezone.utc).isoformat()

        async def _execute():
            try:
                async with self.driver.session() as session:
                    # 1. Pre-Fetch existing properties
                    fetch_query = "MATCH (p:Property) RETURN p.name AS prop_name"
                    result = await session.run(fetch_query)
                    records = await result.data()
                    known_properties = [r["prop_name"] for r in records if r.get("prop_name")]

                    # 2. Extract
                    entities = await self._extract_entities(summary_ref, known_properties)
                    new_props = entities["new_properties"]
                    existing_props = entities["existing_properties"]

                    if not new_props and not existing_props:
                        logger.info("[GRAPH] No entities extracted — skipping graph update.")
                        return

                    # 3. Create/Merge Session Node
                    session_query = """
                    MERGE (u:User {name: $user_name})
                    MERGE (s:Session {session_id: $session_id})
                      ON CREATE SET s.summary_ref = $summary_ref, s.date = $date_iso
                    """
                    await session.run(
                        session_query,
                        user_name=user_name,
                        session_id=session_id,
                        summary_ref=summary_ref[:500],
                        date_iso=date_iso,
                    )
                    logger.info(f"[GRAPH] Session node created: {session_id[:8]}...")

                    # 4. Handle New Properties
                    for prop in new_props:
                        prop_name = prop.get("name")
                        prop_type = str(prop.get("type", "PROJECTS")).upper()
                        if prop_type not in ["PROJECT", "SKILLS", "PROJECTS", "SKILL"]:
                            prop_type = "PROJECTS"
                        cat_name = "PROJECTS" if "PROJECT" in prop_type else "SKILLS"
                        
                        if prop_name:
                            new_query = """
                            MATCH (u:User {name: $user_name})
                            MATCH (s:Session {session_id: $session_id})
                            MATCH (c:Category {name: $cat_name})
                            MERGE (p:Property {name: $prop_name})
                            MERGE (p)-[:BELONGS_TO]->(c)
                            MERGE (s)-[:MENTIONED_IN]->(p)
                            MERGE (u)-[:HAS_PROPERTY]->(p)
                            """
                            await session.run(new_query, 
                                user_name=user_name, 
                                session_id=session_id, 
                                cat_name=cat_name, 
                                prop_name=prop_name
                            )
                            logger.info(f"[GRAPH] New property linked: {prop_name}")

                    # 5. Handle Existing Properties
                    for prop_name in existing_props:
                        if prop_name:
                            existing_query = """
                            MATCH (u:User {name: $user_name})
                            MATCH (s:Session {session_id: $session_id})
                            MERGE (p:Property {name: $prop_name})
                            MERGE (s)-[:MENTIONED_IN]->(p)
                            MERGE (u)-[:HAS_PROPERTY]->(p)
                            """
                            await session.run(existing_query, 
                                user_name=user_name, 
                                session_id=session_id, 
                                prop_name=prop_name
                            )
                            logger.info(f"[GRAPH] Existing property linked: {prop_name}")

                logger.info(
                    f"[GRAPH] Graph updated for session {session_id[:8]}: "
                    f"{len(new_props)} new, {len(existing_props)} existing."
                )
            except Exception as e:
                logger.error(f"[GRAPH] Cypher execution failed: {e}")

        asyncio.create_task(_execute())

    # ── Query Helpers ───────────────────────────────────────────────────
    async def fetch_property_cluster(self, property_name: str) -> list[str]:
        """
        [CLUSTER SEARCH]
        Finds all session IDs where a property was mentioned.
        """
        if not self.driver:
            return []

        cypher = """
        MATCH (p:Property {name: $name})<-[:MENTIONED_IN]-(s:Session)
        RETURN s.session_id AS session_id
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, name=property_name.strip())
                records = await result.data()
                return [r["session_id"] for r in records if r.get("session_id")]
        except Exception as e:
            logger.error(f"[GRAPH] fetch_property_cluster failed: {e}")
            return []

    async def query_related_sessions(self, query_term: str, limit: int = 3) -> list[str]:
        """
        Finds session_ids related to a query term by traversing
        User→Property→Session relationships.
        """
        if not self.driver:
            return []

        cypher = """
        MATCH (s:Session)-[:MENTIONED_IN]->(p:Property)
        WHERE toLower($q) CONTAINS toLower(p.name) OR toLower(p.name) CONTAINS toLower($q)
        RETURN DISTINCT s.session_id AS session_id
        LIMIT $limit
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, q=query_term.strip(), limit=limit)
                records = await result.data()
                return [r["session_id"] for r in records if r.get("session_id")]
        except Exception as e:
            logger.error(f"[GRAPH] Session query failed: {e}")
            return []

    async def get_user_identity(self, user_name: str = "KARTHIK") -> dict:
        """
        [IDENTITY-FIRST PROTOCOL]
        Retrieves all Properties associated with the User node, categorized.
        """
        if not self.driver:
            return {"name": user_name, "skills": [], "projects": [], "properties": []}

        cypher = """
        MATCH (u:User {name: $user_name})
        OPTIONAL MATCH (u)-[:HAS_PROPERTY]->(p:Property)
        OPTIONAL MATCH (p)-[:BELONGS_TO]->(c:Category)
        RETURN u.name AS name,
               collect(DISTINCT CASE WHEN c.name = 'SKILLS' THEN p.name END) AS skills,
               collect(DISTINCT CASE WHEN c.name = 'PROJECTS' THEN p.name END) AS projects,
               collect(DISTINCT p.name) AS properties
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, user_name=user_name)
                record = await result.single()
                if record:
                    return {
                        "name": record["name"],
                        "skills": [s for s in record["skills"] if s],
                        "projects": [pr for pr in record["projects"] if pr],
                        "properties": [p for p in record["properties"] if p],
                    }
        except Exception as e:
            logger.error(f"[GRAPH] Identity retrieval failed: {e}")
        return {"name": user_name, "skills": [], "projects": [], "properties": []}

l3_manager = L3GraphManager()
