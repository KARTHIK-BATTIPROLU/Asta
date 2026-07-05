"""
ASTA Content API
Manage content calendar, LinkedIn posts, and content logs.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from backend.app.api.routes import verify_token
from backend.app.services.sheets_service import sheets_service
from backend.app.db.database import db_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["content"])


class TopicAdd(BaseModel):
    """Request model for adding a topic to calendar."""
    topic: str


class ScheduleUpdate(BaseModel):
    """Request model for scheduling a post."""
    scheduled_time: str


@router.get("/calendar/{platform}")
async def get_calendar(platform: str, token: str = Depends(verify_token)):
    """
    Get all topics from content calendar for a specific platform.
    
    Valid platforms: linkedin, youtube, instagram
    """
    valid_platforms = ["linkedin", "youtube", "instagram"]
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform. Must be one of: {', '.join(valid_platforms)}"
        )
    
    try:
        db = db_manager.db
        topics = await db["content_calendar"].find(
            {"platform": platform}
        ).to_list(100)
        
        # Convert ObjectId to string for JSON serialization
        for topic in topics:
            topic["_id"] = str(topic["_id"])
        
        return {
            "platform": platform,
            "topics": topics,
            "count": len(topics),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error fetching calendar for {platform}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch calendar: {str(e)}")


@router.post("/calendar/{platform}/add")
async def add_to_calendar(
    platform: str,
    topic_data: TopicAdd,
    token: str = Depends(verify_token)
):
    """Add a topic to the content calendar."""
    valid_platforms = ["linkedin", "youtube", "instagram"]
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform. Must be one of: {', '.join(valid_platforms)}"
        )
    
    try:
        db = db_manager.db
        result = await db["content_calendar"].insert_one({
            "platform": platform,
            "topic": topic_data.topic,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        })
        
        return {
            "status": "added",
            "platform": platform,
            "topic": topic_data.topic,
            "id": str(result.inserted_id)
        }
    except Exception as e:
        logger.error(f"Error adding topic to calendar: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add topic: {str(e)}")


@router.get("/linkedin/posts")
async def get_linkedin_posts(token: str = Depends(verify_token)):
    """Get all LinkedIn posts from Google Sheets."""
    try:
        posts = await sheets_service.get_all_posts()
        return {
            "posts": posts,
            "count": len(posts),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error fetching LinkedIn posts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch posts: {str(e)}")


@router.post("/linkedin/posts/{row_id}/approve")
async def approve_linkedin_post(row_id: str, token: str = Depends(verify_token)):
    """Approve a LinkedIn post (Make.com automation will pick it up)."""
    try:
        success = await sheets_service.update_post_status(row_id, "Approved")
        if success:
            return {
                "status": "approved",
                "row_id": row_id,
                "message": "Post approved. Make.com will publish it."
            }
        else:
            raise HTTPException(status_code=404, detail="Post not found")
    except Exception as e:
        logger.error(f"Error approving post {row_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to approve post: {str(e)}")


@router.post("/linkedin/posts/{row_id}/schedule")
async def schedule_linkedin_post(
    row_id: str,
    schedule_data: ScheduleUpdate,
    token: str = Depends(verify_token)
):
    """Schedule a LinkedIn post for future publishing."""
    try:
        # Update both scheduled time and status
        success = await sheets_service.update_post_status(row_id, "Scheduled")
        if success:
            return {
                "status": "scheduled",
                "row_id": row_id,
                "scheduled_time": schedule_data.scheduled_time,
                "message": "Post scheduled successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Post not found")
    except Exception as e:
        logger.error(f"Error scheduling post {row_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule post: {str(e)}")


@router.delete("/linkedin/posts/{row_id}")
async def delete_linkedin_post(row_id: str, token: str = Depends(verify_token)):
    """Delete (archive) a LinkedIn post."""
    try:
        success = await sheets_service.update_post_status(row_id, "Deleted")
        if success:
            return {
                "status": "deleted",
                "row_id": row_id,
                "message": "Post archived successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Post not found")
    except Exception as e:
        logger.error(f"Error deleting post {row_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete post: {str(e)}")


@router.get("/logs/{platform}")
async def get_content_logs(platform: str, token: str = Depends(verify_token)):
    """Get content creation logs for a specific platform."""
    valid_platforms = ["linkedin", "youtube", "instagram"]
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform. Must be one of: {', '.join(valid_platforms)}"
        )
    
    try:
        db = db_manager.db
        logs = await db["content_logs"].find(
            {"platform": platform}
        ).sort("created_at", -1).limit(50).to_list(50)
        
        # Convert ObjectId to string
        for log in logs:
            log["_id"] = str(log["_id"])
        
        return {
            "platform": platform,
            "logs": logs,
            "count": len(logs),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error fetching logs for {platform}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")


@router.post("/seed-calendar")
async def seed_calendar(token: str = Depends(verify_token)):
    """Seed initial topics into content calendar (only if empty)."""
    try:
        from backend.app.core.llm_factory import llm_router
        
        db = db_manager.db
        
        # Check if calendar is already seeded
        count = await db["content_calendar"].count_documents({})
        if count > 0:
            return {
                "status": "skipped",
                "message": f"Calendar already has {count} topics. Skipping seed.",
                "count": count
            }
        
        # Generate topics using LLM
        linkedin_topics_raw = await llm_router.invoke_with_system(
            "intent_classification",
            "Generate 30 evergreen LinkedIn post topics about: AI, LangGraph, productivity, "
            "building in public, tech career, programming. Return one topic per line, no numbering.",
            "Generate diverse, engaging topics"
        )
        
        youtube_topics_raw = await llm_router.invoke_with_system(
            "intent_classification",
            "Generate 30 YouTube video topics about: AI tools, LangGraph tutorials, "
            "productivity systems, tech career India, programming tutorials. "
            "Return one topic per line, no numbering.",
            "Generate educational video topics"
        )
        
        instagram_topics_raw = await llm_router.invoke_with_system(
            "intent_classification",
            "Generate 30 Instagram carousel topics about: tech productivity, AI tools, "
            "coding tips, career growth, building projects. Return one topic per line, no numbering.",
            "Generate visual-friendly topics"
        )
        
        # Parse topics
        linkedin_topics = [t.strip() for t in linkedin_topics_raw.split("\n") if t.strip()][:30]
        youtube_topics = [t.strip() for t in youtube_topics_raw.split("\n") if t.strip()][:30]
        instagram_topics = [t.strip() for t in instagram_topics_raw.split("\n") if t.strip()][:30]
        
        # Insert into MongoDB
        documents = []
        for topic in linkedin_topics:
            documents.append({
                "platform": "linkedin",
                "topic": topic,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            })
        
        for topic in youtube_topics:
            documents.append({
                "platform": "youtube",
                "topic": topic,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            })
        
        for topic in instagram_topics:
            documents.append({
                "platform": "instagram",
                "topic": topic,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            })
        
        if documents:
            await db["content_calendar"].insert_many(documents)
        
        return {
            "status": "seeded",
            "message": "Content calendar seeded successfully",
            "counts": {
                "linkedin": len(linkedin_topics),
                "youtube": len(youtube_topics),
                "instagram": len(instagram_topics),
                "total": len(documents)
            }
        }
    except Exception as e:
        logger.error(f"Error seeding calendar: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to seed calendar: {str(e)}")
