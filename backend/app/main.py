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
logger = logging.getLogger("ASTA_Main")

app = FastAPI(title="ASTA Backend")

# -------------------------------------------------------------------
# Poller Management
# -------------------------------------------------------------------
class PollerManager:
    def __init__(self):
        self._running = False
        self._task = None
        self._interval = 30  # seconds

    async def start(self):
        """Starts the background poller if enabled."""
        if not config.POLLING_ENABLED:
            logger.warning("Background Poller is DISABLED via config (POLLING_ENABLED=false).")
            return

        if self._running:
            logger.warning("Poller is already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Background Poller STARTED.")

    async def stop(self):
        """Gracefully stops the background poller."""
        if not self._running:
            return
            
        logger.info("Stopping Background Poller...")
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Background Poller STOPPED.")

    async def _loop(self):
        """Main polling loop with error handling and graceful shutdown check."""
        count = 0
        while self._running:
            try:
                should_log = config.DEBUG_POLLING or (count % 10 == 0)
                
                if should_log:
                    logger.info(f"Poller tick (cycle {count})...")
                
                # Execute logic (async or sync wrapper)
                if asyncio.iscoroutinefunction(process_reminders):
                    await process_reminders()
                else:
                    await asyncio.to_thread(process_reminders)
                
            except asyncio.CancelledError:
                logger.info("Poller task cancelled.")
                break
            except Exception as e:
                logger.error(f"Poller Exception: {e}", exc_info=True)
                # Brief pause on error to avoid rapid failure loops
                await asyncio.sleep(5)
            
            # Wait for next interval
            count += 1
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                logger.info("Poller sleep interrupted.")
                break

# Global Poller Instance
poller_manager = PollerManager()

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
    except Exception as e:
        logger.warning(f"Config validation warning: {e}")

    # 2. Database
    try:
        MongoDB.connect()
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")

    # 3. Start Poller
    await poller_manager.start()


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup resources on shutdown.
    """
    logger.info("Shutting down ASTA Backend...")
    
    # 1. Stop Poller
    await poller_manager.stop()

    # 2. Close DB
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
    # Expose poller status for debugging
    return {
        "debug": "working", 
        "poller_running": poller_manager._running,
        "polling_enabled": getattr(config, "POLLING_ENABLED", "unknown"),
        "routes_mounted": [route.path for route in app.routes]
    }

# Mount API Router
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    # Local development run
    uvicorn.run(app, host="0.0.0.0", port=8000)
