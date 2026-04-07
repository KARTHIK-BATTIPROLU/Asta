from fastapi import APIRouter
from pydantic import BaseModel
from backend.app.db.mongo import MongoDB
from backend.app.services.llm_service import stream_llm_response
from backend.app.services.deepgram_tts import text_to_speech
from backend.app.core.circuit_breaker import status_registry
import logging
import base64
import time

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    voice_enabled: bool = False
    session_id: str | None = None

@router.get("/health")
def health_check():
    """Enhanced health check with circuit breaker status and memory tier health."""
    mongo_status = "connected" if MongoDB.client else "disconnected"
    
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
            "l3_graph": health_report.get("circuit_l3_graph", {})
        }
    }

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

@router.post("/chat")
async def handle_chat(req: ChatRequest):
    logger.info(f"POST /api/chat received text: {req.message}")

    full_reply = ""
    try:
        # Get current memory mode for health-aware LLM inference
        memory_mode = status_registry.get_memory_mode()
        
        async for token in stream_llm_response(req.message, session_id=req.session_id, health_status=memory_mode):
            if token:
                full_reply += token
    except Exception as e:
        logger.error(f"Error during LLM execution in handle_chat: {e}")
        full_reply = "I'm sorry, I encountered an error answering your text."
    audio_base64 = None
    if req.voice_enabled and full_reply.strip():
        try:
            tts_audio = await text_to_speech(full_reply.strip())
            if tts_audio:
                audio_base64 = base64.b64encode(tts_audio).decode('utf-8')
        except Exception as e:
            logger.error(f"TTS stream error in handle_chat: {e}")

    return {
        "reply": full_reply,
        "audio_base64": audio_base64
    }
