import asyncio
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
