import os

main_py_content = r'''import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import config
from backend.app.db.mongo import MongoDB
from backend.app.api.routes import router
from reminder_agent.poller import process_reminders

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ASTA Backend")

# -------------------------------------------------------------------
# Middleware
# -------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Background Poller Task
# -------------------------------------------------------------------
async def run_poller():
    """
    Runs the reminder poller in the background every 30 seconds.
    Ensures transient errors don't crash the main application.
    """
    logger.info("Background Poller Started")
    while True:
        try:
            logger.info("Poller tick...")
            # If process_reminders is async, await it directly.
            # If it's sync, wrap in asyncio.to_thread(process_reminders)
            if asyncio.iscoroutinefunction(process_reminders):
                await process_reminders()
            else:
                await asyncio.to_thread(process_reminders)
                
        except Exception as e:
            logger.error(f"Poller Error: {e}", exc_info=True)
        
        await asyncio.sleep(30)

# -------------------------------------------------------------------
# LifeCycle Events
# -------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    """
    Initialize resources on startup:
    1. Validate Config
    2. Connect to Database
    3. Start Background Poller
    """
    logger.info("Starting up ASTA Backend...")
    
    # 1. Config
    try:
        if hasattr(config, "validate"):
            config.validate()
        else:
            logger.info("Config validation skipped (method not found)")
    except Exception as e:
        logger.warning(f"Config validation warning: {e}")

    # 2. Database
    try:
        MongoDB.connect()
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")

    # 3. Start Poller (Fire and Forget)
    asyncio.create_task(run_poller())


@app.on_event("shutdown")
def shutdown_event():
    """
    Cleanup resources on shutdown.
    """
    logger.info("Shutting down ASTA Backend...")
    if MongoDB.client:
        MongoDB.client.close()
        logger.info("MongoDB connection closed")

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "alive", "service": "ASTA Backend"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug")
def debug():
    # Helper for debugging
    paths = [route.path for route in app.routes]
    return {"debug": "working", "routes_mounted": paths}

# Mount API Router
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    # Local development run
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''

routes_py_content = r'''import base64
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
'''

# Use os.path.join for correct path handling
base_dir = os.getcwd()
main_path = os.path.join(base_dir, "backend", "app", "main.py")
routes_path = os.path.join(base_dir, "backend", "app", "api", "routes.py")

with open(main_path, "w", encoding="utf-8") as f:
    f.write(main_py_content)
    print(f"Updated {main_path}")

with open(routes_path, "w", encoding="utf-8") as f:
    f.write(routes_py_content)
    print(f"Updated {routes_path}")
