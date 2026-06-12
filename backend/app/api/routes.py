"""
ASTA HTTP API routes.

All MongoDB operations delegated to db_manager. No direct PyMongo imports.
"""

import os
import hmac
import logging
import base64
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from backend.app.db.database import db_manager
from backend.app.services.llm_service import stream_llm_response
from backend.app.services.deepgram_tts import text_to_speech
from backend.app.core.circuit_breaker import status_registry
from backend.app.api.ws_routes import fetch_memory_context
from backend.app.services.l1_cache import l1_manager
from backend.app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    voice_enabled: bool = False
    session_id: str | None = None
    workflow_hint: str | None = None  # Optional workflow hint for supervisor


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    audio_base64: str | None = None


@router.get("/health")
async def health_check():
    """Enhanced health check with circuit breaker status and memory tier health."""
    mongo_status = "connected" if (db_manager.mongo_client and not db_manager.degraded_mode) else "disconnected"

    # Get circuit breaker and memory tier health
    health_report = status_registry.get_all_health()
    memory_mode = status_registry.get_memory_mode()
    status_summary = status_registry.get_status_summary()

    return {
        "status": "ok" if mongo_status == "connected" else "degraded",
        "timestamp": time.time(),
        "database": mongo_status,
        "memory_mode": memory_mode,
        "services": status_summary,
        "circuit_breakers": {
            "l2_vector": health_report.get("circuit_l2_vector", {}),
            "l3_graph": health_report.get("circuit_l3_graph", {}),
        },
        "tools": _get_tool_status(),
    }


def _get_tool_status() -> dict:
    """Get registered tool names for health check."""
    try:
        from backend.app.tools.tool_registry import tool_registry
        return {"registered": tool_registry.tool_names, "count": len(tool_registry.tool_names)}
    except Exception:
        return {"registered": [], "count": 0}


@router.get("/health/circuits")
def circuit_status():
    """Detailed circuit breaker status endpoint for monitoring."""
    return status_registry.get_all_health()


@router.post("/admin/reset/circuit/{circuit_name}")
def reset_circuit(circuit_name: str):
    """Manually force a circuit breaker to close."""
    logger.info(f"Manual override: Resetting circuit {circuit_name}")
    circuit = status_registry.get_circuit_breaker(circuit_name)
    if circuit:
        circuit.force_close()
        return {"status": "success", "message": f"Circuit {circuit_name} manually reset (force closed)"}
    return {"status": "error", "message": f"Circuit {circuit_name} not found"}


security = HTTPBearer()

_API_BEARER_TOKEN = os.getenv("ASTA_API_BEARER_TOKEN", "").strip()


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not _API_BEARER_TOKEN:
        raise HTTPException(status_code=500, detail="ASTA_API_BEARER_TOKEN not configured")
    if not hmac.compare_digest(credentials.credentials, _API_BEARER_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


@router.post("/chat", response_model=ChatResponse)
async def handle_chat(req: ChatRequest, token: str = Depends(verify_token)):
    logger.info(f"POST /api/chat received text: {req.message}")

    full_reply = ""
    session_id = req.session_id or str(uuid.uuid4())
    try:
        # Use the supervisor LangGraph for orchestration
        from backend.app.core.supervisor_graph import run_supervisor_graph

        # Fetch conversation history (best-effort; memory context is injected by the graph)
        history = []
        try:
            history, _ = await fetch_memory_context(req.message, session_id)
        except Exception as mem_err:
            logger.error(f"[Chat] Error fetching memory context: {mem_err}")

        # Run supervisor graph (classifies intent + routes + checkpoints)
        result = await run_supervisor_graph(
            session_id=session_id,
            user_input=req.message,
            messages=history or [],
        )

        full_reply = result.get("response", "")

        # Save to session
        if full_reply.strip():
            try:
                await SessionManager.add_message(session_id, "user", req.message)
                await SessionManager.add_message(session_id, "assistant", full_reply.strip())
            except Exception as e:
                logger.error(f"POST /api/chat Error saving messages to SessionManager: {e}")

    except Exception as e:
        logger.error(f"Error during supervisor execution in handle_chat: {e}")
        full_reply = "I'm sorry, I encountered an error answering your text."
    
    audio_base64 = None
    if req.voice_enabled and full_reply.strip():
        try:
            tts_audio = await text_to_speech(full_reply.strip())
            if tts_audio:
                audio_base64 = base64.b64encode(tts_audio).decode("utf-8")
        except Exception as e:
            logger.error(f"TTS stream error in handle_chat: {e}")

    logger.info(f"POST /api/chat returning reply length: {len(full_reply)}, audio included: {audio_base64 is not None}")
    logger.debug(f"POST /api/chat full reply text: {full_reply}")

    return ChatResponse(session_id=session_id, reply=full_reply, audio_base64=audio_base64)
