"""
Neo4j Schema Initialization for ASTA
Idempotent script to create base graph structure
Safe to run multiple times
"""
import logging
import asyncio
import os
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SchemaInit")


async def initialize_schema():
    """
    Initialize Neo4j base schema for ASTA.
    Creates:
    - KARTHIK Person node
    - All 6 categories
    - Skill groups
    - Pre-seed nodes (Python, FastAPI, MongoDB, Neo4j, Pinecone, Groq, ASTA, all tools)
    
    Uses MERGE everywhere - safe to run multiple times.
    """
    
    # Get Neo4j credentials
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USERNAME")
    neo4j_pass = os.getenv("NEO4J_PASSWORD")
    
    if not all([neo4j_uri, neo4j_user, neo4j_pass]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD required")
    
    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_pass),
        connection_timeout=5.0
    )
    
    try:
        async with driver.session() as session:
            logger.info("Starting schema initialization...")
            
            # Step 1: Create KARTHIK Person node
            logger.info("Creating KARTHIK Person node...")
            await session.run("""
                MERGE (p:Person {name: "Karthik"})
                ON CREATE SET p.created_at = datetime()
            """)
            
            # Step 2: Create all 6 categories
            logger.info("Creating categories...")
            await session.run("""
                MERGE (p:Person {name: "Karthik"})
                
                MERGE (skills:Category {name: "Skills"})
                ON CREATE SET skills.created_at = datetime()
                
                MERGE (projects:Category {name: "Projects"})
                ON CREATE SET projects.created_at = datetime()
                
                MERGE (tools:Category {name: "Tools"})
                ON CREATE SET tools.created_at = datetime()
                
                MERGE (interests:Category {name: "Interests"})
                ON CREATE SET interests.created_at = datetime()
                
                MERGE (people:Category {name: "People"})
                ON CREATE SET people.created_at = datetime()
                
                MERGE (commitments:Category {name: "Commitments"})
                ON CREATE SET commitments.created_at = datetime()
                
                MERGE (p)-[:HAS_CATEGORY]->(skills)
                MERGE (p)-[:HAS_CATEGORY]->(projects)
                MERGE (p)-[:HAS_CATEGORY]->(tools)
                MERGE (p)-[:HAS_CATEGORY]->(interests)
                MERGE (p)-[:HAS_CATEGORY]->(people)
                MERGE (p)-[:HAS_CATEGORY]->(commitments)
            """)
            
            # Step 3: Create skill groups
            logger.info("Creating skill groups...")
            await session.run("""
                MERGE (skills:Category {name: "Skills"})
                
                MERGE (prog_langs:SkillGroup {name: "Programming Languages"})
                ON CREATE SET prog_langs.created_at = datetime()
                
                MERGE (frameworks:SkillGroup {name: "Frameworks"})
                ON CREATE SET frameworks.created_at = datetime()
                
                MERGE (databases:SkillGroup {name: "Databases"})
                ON CREATE SET databases.created_at = datetime()
                
                MERGE (dev_tools:SkillGroup {name: "Dev Tools"})
                ON CREATE SET dev_tools.created_at = datetime()
                
                MERGE (ai_ml:SkillGroup {name: "AI & ML"})
                ON CREATE SET ai_ml.created_at = datetime()
                
                MERGE (skills)-[:CONTAINS]->(prog_langs)
                MERGE (skills)-[:CONTAINS]->(frameworks)
                MERGE (skills)-[:CONTAINS]->(databases)
                MERGE (skills)-[:CONTAINS]->(dev_tools)
                MERGE (skills)-[:CONTAINS]->(ai_ml)
            """)
            
            # Step 4: Pre-seed programming languages
            logger.info("Pre-seeding programming languages...")
            await session.run("""
                MERGE (prog_langs:SkillGroup {name: "Programming Languages"})
                
                MERGE (python:Skill {name: "Python"})
                ON CREATE SET python.created_at = datetime()
                
                MERGE (prog_langs)-[:CONTAINS]->(python)
            """)
            
            # Step 5: Pre-seed frameworks
            logger.info("Pre-seeding frameworks...")
            await session.run("""
                MERGE (frameworks:SkillGroup {name: "Frameworks"})
                
                MERGE (fastapi:Skill {name: "FastAPI"})
                ON CREATE SET fastapi.created_at = datetime()
                
                MERGE (frameworks)-[:CONTAINS]->(fastapi)
            """)
            
            # Step 6: Pre-seed databases
            logger.info("Pre-seeding databases...")
            await session.run("""
                MERGE (databases:SkillGroup {name: "Databases"})
                
                MERGE (mongodb:Skill {name: "MongoDB"})
                ON CREATE SET mongodb.created_at = datetime()
                
                MERGE (neo4j:Skill {name: "Neo4j"})
                ON CREATE SET neo4j.created_at = datetime()
                
                MERGE (pinecone:Skill {name: "Pinecone"})
                ON CREATE SET pinecone.created_at = datetime()
                
                MERGE (databases)-[:CONTAINS]->(mongodb)
                MERGE (databases)-[:CONTAINS]->(neo4j)
                MERGE (databases)-[:CONTAINS]->(pinecone)
            """)
            
            # Step 7: Pre-seed AI & ML
            logger.info("Pre-seeding AI & ML...")
            await session.run("""
                MERGE (ai_ml:SkillGroup {name: "AI & ML"})
                
                MERGE (groq:Skill {name: "Groq"})
                ON CREATE SET groq.created_at = datetime()
                
                MERGE (ai_ml)-[:CONTAINS]->(groq)
            """)
            
            # Step 8: Pre-seed ASTA project
            logger.info("Pre-seeding ASTA project...")
            await session.run("""
                MERGE (projects:Category {name: "Projects"})
                
                MERGE (asta:Project {name: "ASTA"})
                ON CREATE SET asta.created_at = datetime(),
                             asta.description = "Personal AI orchestrator"
                
                MERGE (projects)-[:CONTAINS]->(asta)
            """)
            
            # Step 9: Pre-seed tools
            logger.info("Pre-seeding tools...")
            await session.run("""
                MERGE (tools:Category {name: "Tools"})
                
                MERGE (notion:Tool {name: "Notion"})
                ON CREATE SET notion.created_at = datetime()
                
                MERGE (calendar:Tool {name: "Google Calendar"})
                ON CREATE SET calendar.created_at = datetime()
                
                MERGE (serper:Tool {name: "Serper Search"})
                ON CREATE SET serper.created_at = datetime()
                
                MERGE (weather:Tool {name: "Weather"})
                ON CREATE SET weather.created_at = datetime()
                
                MERGE (gemini:Tool {name: "Gemini"})
                ON CREATE SET gemini.created_at = datetime()
                
                MERGE (tools)-[:CONTAINS]->(notion)
                MERGE (tools)-[:CONTAINS]->(calendar)
                MERGE (tools)-[:CONTAINS]->(serper)
                MERGE (tools)-[:CONTAINS]->(weather)
                MERGE (tools)-[:CONTAINS]->(gemini)
            """)
            
            logger.info("✅ Schema initialization complete!")
            
            # Verify
            result = await session.run("""
                MATCH (n)
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY label
            """)
            
            records = await result.data()
            logger.info("\nNode counts:")
            for record in records:
                logger.info(f"  {record['label']}: {record['count']}")
    
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(initialize_schema())
