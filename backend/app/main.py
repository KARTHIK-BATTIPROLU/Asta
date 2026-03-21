from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from backend.app.config import config
from backend.app.db.mongo import MongoDB
from reminder_agent.poller import process_reminders

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import router securely after logger is configured
try:
    from backend.app.api.routes import router
    logger.info("Imported router successfully.")
except Exception as e:
    logger.error(f"Failed to import router: {e}")
    # Create empty router to prevent app crash but log loudly
    router = APIRouter()

app = FastAPI(title="ASTA API")

# Background Poller Task
async def run_poller():
    """
    Runs the reminder poller in the background.
    Polls every 30 seconds.
    """
    logger.info("Background Poller Started")
    while True:
        try:
            # Reusing existing async poller logic
            await process_reminders()
        except Exception as e:
            logger.error(f"Background Poller Error: {e}")
        
        # Wait 30 seconds before next poll
        await asyncio.sleep(30)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to DB on startup & Start Poller
@app.on_event("startup")
async def startup_event():
    # 1. Validate Config
    config.validate()
    
    # 2. Connect Backend DB
    MongoDB.connect()
    logger.info("Connected to MongoDB")
    
    # 3. Start Background Poller
    asyncio.create_task(run_poller())

@app.on_event("shutdown")
def shutdown_db_client():
    if MongoDB.client:
        MongoDB.client.close()
        logger.info("Closed MongoDB connection")

# Health Check
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ASTA API", "version": "1.0.0"}

# Root Endpoint (For Render ping)
@app.get("/")
def root():
    return {"status": "alive", "message": "ASTA API is running"}

# Include Routes
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    # Add project root to sys.path to ensure module resolution works
    import sys
    import os
    sys.path.append(os.getcwd())
    
    logger.info("Starting ASTA API server...")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)