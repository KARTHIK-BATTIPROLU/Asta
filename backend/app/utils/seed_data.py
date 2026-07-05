"""
ASTA Seed Data
Seeds MongoDB with initial content calendar topics on first run.
"""
import logging
from backend.app.db.database import db_manager

logger = logging.getLogger(__name__)


async def seed_if_empty():
    """Seed MongoDB with initial data if collections are empty."""
    try:
        db = db_manager.db
        
        # Seed LinkedIn calendar (30 topics)
        count = await db["content_calendar"].count_documents({"platform": "linkedin"})
        if count == 0:
            linkedin_topics = [
                "Why most developers never ship their side projects",
                "What I learned building an AI assistant from scratch",
                "The real reason junior developers get stuck",
                "Stop using TODO comments — do this instead",
                "5 things AI cannot replace in software engineering",
                "How to think like a senior developer in 6 months",
                "The honest truth about 'passive income' in tech",
                "Why your portfolio doesn't matter as much as you think",
                "Building in public changed how I learn — here's why",
                "The difference between a 1x and 10x developer is this",
                "I studied 100 LinkedIn posts that went viral — patterns I found",
                "How to get your first 500 LinkedIn followers as a developer",
                "LangChain vs LangGraph — what actually matters",
                "AI agents will not replace developers — here's what they will do",
                "How I went from confused student to CTO in 2 years",
                "The productivity system that finally works for developers",
                "Why consistency beats talent in tech every single time",
                "Open source changed my career — here's the honest story",
                "What no one tells you about leading a student community",
                "The most underrated skill in software engineering",
                "How to learn faster by building things that break",
                "The problem with 'learn in 30 days' content",
                "Why I almost quit coding and what made me stay",
                "Building AI products without a computer science degree",
                "The mental model that changed how I approach problems",
                "How to get noticed by recruiters without cold applying",
                "What the metaverse actually means for developers now",
                "Why your side project is a better resume than your resume",
                "The honest guide to staying consistent when you're demotivated",
                "How to use AI tools without becoming dependent on them",
            ]
            await db["content_calendar"].insert_many([
                {"platform": "linkedin", "topic": t, "status": "pending", "source": "default"}
                for t in linkedin_topics
            ])
            logger.info(f"Seeded {len(linkedin_topics)} LinkedIn topics")
        
        # Seed YouTube calendar (30 topics)
        yt_count = await db["content_calendar"].count_documents({"platform": "youtube"})
        if yt_count == 0:
            youtube_topics = [
                "Build a personal AI assistant with LangGraph from scratch",
                "LangGraph explained — nodes, edges, state in 10 minutes",
                "How I built my memory system inspired by how humans remember",
                "Neo4j for beginners — knowledge graphs actually explained",
                "The complete guide to AI agents in 2026",
                "FastAPI + LangGraph — production-grade AI backend",
                "How Retrieval Augmented Generation actually works",
                "Building a voice assistant with Deepgram and Python",
                "My productivity system as a developer and CTO",
                "How to use Pinecone for semantic memory in AI apps",
                "Building in public — what I learned after 6 months",
                "The truth about the Indian tech scene in 2026",
                "How to go from student to developer — my honest journey",
                "Vector databases explained — when to use which",
                "From idea to deployed AI app — complete walkthrough",
                "How I manage a 300-person student community",
                "Redis for AI applications — caching and hot storage",
                "Building AI products on a student budget",
                "The metaverse is not dead — here's what's actually happening",
                "How to contribute to open source as a beginner",
                "LangChain vs LangGraph — practical comparison",
                "Building a research assistant with web scraping and AI",
                "How to think in systems — mental models for developers",
                "The complete guide to prompt engineering in 2026",
                "Why I chose Python for AI development",
                "Building a Notion integration with Python",
                "Async Python explained — building fast AI backends",
                "How to stay consistent when building side projects",
                "The honest guide to learning DSA as a working developer",
                "AI tools I use daily as a developer and CTO",
            ]
            await db["content_calendar"].insert_many([
                {"platform": "youtube", "topic": t, "status": "pending", "source": "default"}
                for t in youtube_topics
            ])
            logger.info(f"Seeded {len(youtube_topics)} YouTube topics")
        
        # Seed Instagram calendar (30 topics - reuse LinkedIn topics)
        insta_count = await db["content_calendar"].count_documents({"platform": "instagram"})
        if insta_count == 0:
            insta_topics = [
                "Why most developers never ship their side projects",
                "What I learned building an AI assistant from scratch",
                "The real reason junior developers get stuck",
                "Stop using TODO comments — do this instead",
                "5 things AI cannot replace in software engineering",
                "How to think like a senior developer in 6 months",
                "The honest truth about 'passive income' in tech",
                "Why your portfolio doesn't matter as much as you think",
                "Building in public changed how I learn — here's why",
                "The difference between a 1x and 10x developer is this",
                "I studied 100 LinkedIn posts that went viral — patterns I found",
                "How to get your first 500 LinkedIn followers as a developer",
                "LangChain vs LangGraph — what actually matters",
                "AI agents will not replace developers — here's what they will do",
                "How I went from confused student to CTO in 2 years",
                "The productivity system that finally works for developers",
                "Why consistency beats talent in tech every single time",
                "Open source changed my career — here's the honest story",
                "What no one tells you about leading a student community",
                "The most underrated skill in software engineering",
                "How to learn faster by building things that break",
                "The problem with 'learn in 30 days' content",
                "Why I almost quit coding and what made me stay",
                "Building AI products without a computer science degree",
                "The mental model that changed how I approach problems",
                "How to get noticed by recruiters without cold applying",
                "What the metaverse actually means for developers now",
                "Why your side project is a better resume than your resume",
                "The honest guide to staying consistent when you're demotivated",
                "How to use AI tools without becoming dependent on them",
            ]
            await db["content_calendar"].insert_many([
                {"platform": "instagram", "topic": t, "status": "pending", "source": "default"}
                for t in insta_topics
            ])
            logger.info(f"Seeded {len(insta_topics)} Instagram topics")
        
        logger.info("Seed data check complete.")
    except Exception as e:
        logger.error(f"Error seeding data: {e}")
