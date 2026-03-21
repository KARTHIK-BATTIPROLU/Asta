import base64
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from backend.app.agents.asta import asta_agent
from backend.app.speech.deepgram_client import deepgram_service
from backend.app.db.mongo import MongoDB

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Request/Response Models ---
class ChatRequest(BaseModel):
    message: str
    voice_enabled: bool = False

class ChatResponse(BaseModel):
    reply: str
    audio_base64: Optional[str] = None

# --- Test Endpoint ---
@router.get("/test", tags=["Debug"])
def test_endpoint():
    """
    Test endpoint to verify router is mounted correctly.
    Access at: GET /api/test
    """
    return {"message": "router working"}

# --- Chat Endpoint ---
@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(request: ChatRequest):
    try:
        logger.info(f"Received chat message: {request.message}")
        
        # Ensure DB Connected
        if MongoDB.client is None:
            logger.info("Connecting to MongoDB lazily...")
            try:
                MongoDB.connect()
            except Exception as e:
                logger.error(f"DB Connect Error: {e}")
                
        # Invoke Agent
        logger.info("Invoking Agent...")
        try:
            reply = asta_agent(request.message)
            logger.info(f"Agent Reply: {reply}")
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            reply = "I'm having trouble thinking right now."
        
        if not reply:
            reply = "I'm sorry, I couldn't generate a response."
        
        # TTS Processing
        audio_b64 = None
        if request.voice_enabled:
            try:
                audio_bytes = await deepgram_service.speak(reply)
                if audio_bytes:
                    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            except Exception as e:
                logger.error(f"TTS Error: {e}")
                # Don't fail the whole request if TTS fails
        
        return ChatResponse(reply=reply, audio_base64=audio_b64)

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Voice Endpoint ---
@router.post("/voice", tags=["Voice"])
async def voice_endpoint(file: UploadFile = File(...)):
    try:
        logger.info("Received voice input")
        
        # 1. Read audio
        audio_bytes = await file.read()
        
        # 2. Transcribe (STT)
        try:
            transcript = await deepgram_service.transcribe(audio_bytes)
            logger.info(f"Transcript: {transcript}")
        except Exception as e:
            logger.error(f"STT Error: {e}")
            return {"reply": "I couldn't hear you clearly.", "transcript": ""}
        
        if not transcript:
             return {"reply": "I couldn't hear you clearly.", "transcript": ""}

        # 3. Process with Agent
        if MongoDB.client is None:
            MongoDB.connect()
            
        reply = asta_agent(transcript)
        
        # 4. Generate Audio (TTS)
        audio_bytes_out = await deepgram_service.speak(reply)
        audio_b64 = None
        if audio_bytes_out:
            audio_b64 = base64.b64encode(audio_bytes_out).decode('utf-8')
            
        return {
            "transcript": transcript,
            "reply": reply,
            "audio_base64": audio_b64
        }

    except Exception as e:
        logger.error(f"Voice error: {e}")
        return {"reply": "Sorry, voice processing failed."}
