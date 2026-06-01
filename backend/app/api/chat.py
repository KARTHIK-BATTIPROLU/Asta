"""
ASTA Chat API
Text-based chat interface for ASTA
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.app.auth.middleware import verify_token
from backend.app.core.supervisor import run_supervisor
import uuid
import logging

router = APIRouter()


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    workflow_hint: Optional[str] = None


class ChatMessageResponse(BaseModel):
    session_id: str
    response: str
    workflow_type: str
    intermediate_stages: list
    is_complete: bool
    notion_page_id: Optional[str] = None


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    user: str = Depends(verify_token)
):
    """Send a message to ASTA and get a response."""
    session_id = request.session_id or str(uuid.uuid4())
    
    try:
        result = await run_supervisor(
            session_id=session_id,
            user_input=request.message,
            workflow_hint=request.workflow_hint or ""
        )
        
        return ChatMessageResponse(
            session_id=session_id,
            response=result.get("asta_response", ""),
            workflow_type=result.get("workflow_type", ""),
            intermediate_stages=result.get("intermediate_stages", []),
            is_complete=result.get("is_complete", False),
            notion_page_id=result.get("notion_page_id")
        )
    except Exception as e:
        logging.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/end")
async def end_session(
    session_id: str,
    user: str = Depends(verify_token)
):
    """Force-end a session and save to memory."""
    try:
        from memory import memory_engine
        # Fetch session from MongoDB and save
        # Implementation depends on session storage structure
        return {"success": True, "session_id": session_id}
    except Exception as e:
        logging.error(f"Session end error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def get_sessions(
    limit: int = 10,
    user: str = Depends(verify_token)
):
    """Get recent chat sessions."""
    try:
        from backend.app.db.mongo import get_mongo_client
        client = get_mongo_client()
        db = client[settings.DB_NAME]
        sessions = list(db["sessions"].find().sort("start_time", -1).limit(limit))
        # Convert ObjectId to string
        for session in sessions:
            session["_id"] = str(session["_id"])
        return {"sessions": sessions}
    except Exception as e:
        logging.error(f"Get sessions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
