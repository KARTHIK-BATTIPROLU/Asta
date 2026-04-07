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
    async def _extract_entities(self, summary_text: str) -> dict:
        """
        Uses Groq JSON mode to extract projects and skills from summary text.
        Returns {"projects": [...], "skills": [...]}.
        """
        try:
            prompt = f"""Extract explicitly named entities from the following text.
Rules:
- A 'project' is an application, system, or software (e.g., 'Maestro', 'Scam Shield', 'GrowHub').
- A 'skill' is a language, framework, technique, or tool (e.g., 'Flutter', 'Federated ML', 'Python').
- Return ONLY valid JSON: {{"projects": ["..."], "skills": ["..."]}}
- If none exist, return empty arrays.

Text: {summary_text}"""

            response = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            data = json.loads(response.choices[0].message.content)
            result = {
                "projects": data.get("projects", []),
                "skills": data.get("skills", [])
            }
            logger.info(f"[GRAPH] Extracted {len(result['projects'])} projects, {len(result['skills'])} skills.")
            return result
        except Exception as e:
            logger.error(f"[GRAPH] Entity extraction failed: {e}")
            return {"projects": [], "skills": []}

    # ── Graph Update Pipeline ───────────────────────────────────────────
    async def update_graph_knowledge(
        self, session_id: str, summary_ref: str, user_name: str = "Karthik"
    ):
        """
        Full graph update pipeline:
        1. Extract entities via LLM
        2. MERGE Session node + link to Person
        3. MERGE Project/Skill nodes + relationships
        All MERGE-based to prevent duplicates.
        Runs as fire-and-forget task to avoid blocking TTS.
        """
        if not self.driver:
            logger.warning("[GRAPH] Neo4j driver unavailable — skipping graph update.")
            return

        entities = await self._extract_entities(summary_ref)
        projects = entities["projects"]
        skills = entities["skills"]

        if not projects and not skills:
            logger.info("[GRAPH] No entities extracted — skipping graph update.")
            return

        date_iso = datetime.now(timezone.utc).isoformat()

        async def _execute():
            try:
                async with self.driver.session() as session:
                    # 1. Session node + link to Person
                    session_query = """
                    MERGE (u:Person {name: $user_name})
                    MERGE (s:Session {session_id: $session_id})
                      ON CREATE SET s.summary_ref = $summary_ref, s.date = $date_iso
                    MERGE (u)-[:HAS_SESSION]->(s)
                    """
                    await session.run(
                        session_query,
                        user_name=user_name,
                        session_id=session_id,
                        summary_ref=summary_ref[:500],  # Truncate — Neo4j is reference only
                        date_iso=date_iso,
                    )
                    logger.info(f"[GRAPH] Session node created: {session_id[:8]}...")

                    # 2. Project nodes + relationships (independent query to avoid cartesian)
                    if projects:
                        project_query = """
                        MATCH (u:Person {name: $user_name})
                        MATCH (s:Session {session_id: $session_id})
                        UNWIND $projects AS project_name
                        MERGE (p:Project {name: project_name})
                        MERGE (u)-[:WORKS_ON]->(p)
                        MERGE (s)-[:RELATES_TO]->(p)
                        """
                        await session.run(
                            project_query,
                            user_name=user_name,
                            session_id=session_id,
                            projects=projects,
                        )
                        for p in projects:
                            logger.info(f"[GRAPH] Project node linked: {p}")

                    # 3. Skill nodes + relationships
                    if skills:
                        skill_query = """
                        MATCH (u:Person {name: $user_name})
                        MATCH (s:Session {session_id: $session_id})
                        UNWIND $skills AS skill_name
                        MERGE (sk:Skill {name: skill_name})
                        MERGE (u)-[:HAS_SKILL]->(sk)
                        MERGE (s)-[:RELATES_TO]->(sk)
                        """
                        await session.run(
                            skill_query,
                            user_name=user_name,
                            session_id=session_id,
                            skills=skills,
                        )
                        for sk in skills:
                            logger.info(f"[GRAPH] Skill node linked: {sk}")

                logger.info(
                    f"[GRAPH] Graph updated for session {session_id[:8]}: "
                    f"{len(projects)} projects, {len(skills)} skills."
                )
            except Exception as e:
                logger.error(f"[GRAPH] Cypher execution failed: {e}")

        # Fire-and-forget to avoid blocking the voice pipeline
        asyncio.create_task(_execute())

    # ── Query Helpers ───────────────────────────────────────────────────
    async def query_related_sessions(self, query_term: str, limit: int = 3) -> list[str]:
        """
        Finds session_ids related to a query term by traversing
        Person→Session→Project/Skill relationships.
        """
        if not self.driver:
            return []

        cypher = """
        MATCH (s:Session)-[:RELATES_TO]->(entity)
        WHERE toLower($q) CONTAINS toLower(entity.name) OR toLower(entity.name) CONTAINS toLower($q)
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

    async def query_projects_by_skill(self, skill_name: str) -> list[str]:
        """Returns project names that co-occur with a skill in sessions."""
        if not self.driver:
            return []

        cypher = """
        MATCH (s:Session)-[:RELATES_TO]->(sk:Skill)
        WHERE toLower(sk.name) CONTAINS toLower($skill_name)
        MATCH (s)-[:RELATES_TO]->(p:Project)
        RETURN DISTINCT p.name AS project_name
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, skill_name=skill_name.strip())
                records = await result.data()
                return [r["project_name"] for r in records]
        except Exception as e:
            logger.error(f"[GRAPH] Project-by-skill query failed: {e}")
            return []

    async def get_full_graph(self) -> list[dict]:
        """Debug helper: returns all nodes and relationships."""
        if not self.driver:
            return []

        cypher = """
        MATCH (a)-[r]->(b)
        RETURN labels(a) AS from_labels, a.name AS from_name,
               type(r) AS relationship,
               labels(b) AS to_labels, b.name AS to_name
        LIMIT 100
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher)
                return await result.data()
        except Exception as e:
            logger.error(f"[GRAPH] Full graph query failed: {e}")
            return []


    async def get_user_identity(self, user_name: str = "Karthik") -> dict:
        """
        [IDENTITY-FIRST PROTOCOL]
        Retrieves base properties, skills, and projects associated with the user node.
        """
        if not self.driver:
            return {"name": user_name, "skills": [], "projects": []}

        cypher = """
        MATCH (u:Person {name: $user_name})
        OPTIONAL MATCH (u)-[:HAS_SKILL]->(sk:Skill)
        OPTIONAL MATCH (u)-[:WORKS_ON]->(p:Project)
        RETURN u.name AS name,
               collect(DISTINCT sk.name) AS skills,
               collect(DISTINCT p.name) AS projects
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, user_name=user_name)
                record = await result.single()
                if record:
                    return {
                        "name": record["name"],
                        "skills": [s for s in record["skills"] if s],
                        "projects": [p for p in record["projects"] if p]
                    }
        except Exception as e:
            logger.error(f"[GRAPH] Identity retrieval failed: {e}")
        return {"name": user_name, "skills": [], "projects": []}

    async def get_project_cluster(self, session_ids: list[str]) -> list[str]:
        """
        [VECTOR-GRAPH STITCH]
        Takes active session IDs (found via vector search) and lights up the Graph.
        Pulls neighbor nodes (Max 2 hops) connected to the Projects interacting with these sessions.
        Returns a list of cluster insights (edges).
        """
        if not self.driver or not session_ids:
            return []

        cypher = """
        UNWIND $session_ids AS sid
        MATCH (s:Session {session_id: sid})-[:RELATES_TO]->(entity)
        OPTIONAL MATCH (entity)-[r]-(neighbor)
        WHERE NOT neighbor:Session AND NOT neighbor:Person AND NOT neighbor:Category
        RETURN DISTINCT labels(entity)[0] AS type1, entity.name AS origin,
                        type(r) AS relation,
                        labels(neighbor)[0] AS type2, neighbor.name AS target
        LIMIT 20
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, session_ids=session_ids)
                records = await result.data()
                clusters = []
                for rec in records:
                    if rec["target"] and rec["origin"] != rec["target"]:
                         clusters.append(f"({rec['type1']} '{rec['origin']}') -[{rec['relation']}]- ({rec['type2']} '{rec['target']}')")
                    else:
                         clusters.append(f"({rec['type1']} '{rec['origin']}') was discussed.")
                return list(set(clusters))
        except Exception as e:
            logger.error(f"[GRAPH] Cluster retrieval failed: {e}")
            return []

l3_manager = L3GraphManager()
