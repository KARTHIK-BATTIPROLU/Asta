import base64
from fastapi import APIRouter, UploadFile, File, Form, Depends
from pydantic import BaseModel
from backend.app.agents.asta import asta_agent
from backend.app.speech.deepgram_client import deepgram_service
from backend.app.db.mongo import MongoDB
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

from typing import Optional

class ChatRequest(BaseModel):
    message: str
    voice_enabled: bool = False

class ChatResponse(BaseModel):
    reply: str
    audio_base64: Optional[str] = None

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        logger.info(f"Received chat message: {request.message}")
        
        # 1. Process with Agent
        # MongoDB connection check (lazy load)
        if MongoDB.client is None:
            logger.info("Connecting to MongoDB lazily...")
            MongoDB.connect()
            
        logger.info("Invoking Agent...")
        reply = asta_agent(request.message)
        logger.info(f"Agent Reply: {reply}")
        
        if not reply:
            reply = "I'm sorry, I couldn't generate a response."
        
        # 2. TTS if voice enabled
        audio_b64 = None
        if request.voice_enabled:
            audio_bytes = await deepgram_service.speak(reply)
            if audio_bytes:
                audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        return ChatResponse(reply=reply, audio_base64=audio_b64)

    except Exception as e:
        logger.error(f"Chat error: {e}")
        return ChatResponse(reply="Sorry, something went wrong.")


@router.post("/voice")
async def voice_endpoint(file: UploadFile = File(...)):
    try:
        logger.info("Received voice input")
        
        # 1. Read audio file
        audio_bytes = await file.read()
        
        # 2. Transcribe (STT)
        transcript = await deepgram_service.transcribe(audio_bytes)
        logger.info(f"Transcript: {transcript}")
        
        if not transcript:
             return {"reply": "I couldn't hear you clearly.", "transcript": ""}

        # 3. Process with Agent
        if MongoDB.client is None:
            MongoDB.connect()
            
        reply = asta_agent(transcript)
        
        # 4. Generate Audio (TTS) - voice always returns audio in this flow usually
        # But let's assume we want audio back since input was voice
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

@router.get("/health")
def health_check():
    return {"status": "ok"}