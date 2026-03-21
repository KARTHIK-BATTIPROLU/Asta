from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio

from backend.app.config import config
from backend.app.db.mongo import MongoDB
from backend.app.api.routes import router
from reminder_agent.poller import process_reminders

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ASTA API")

# -------------------------------
# Background Poller
# -------------------------------
async def run_poller():
    logger.info("Background Poller Started")
    while True:
        try:
            await process_reminders()
        except Exception as e:
            logger.error(f"Poller Error: {e}")
        await asyncio.sleep(30)

# -------------------------------
# Middleware
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Startup / Shutdown
# -------------------------------
@app.on_event("startup")
async def startup_event():
    config.validate()
    MongoDB.connect()
    logger.info("Connected to MongoDB")

    asyncio.create_task(run_poller())


@app.on_event("shutdown")
def shutdown_event():
    if MongoDB.client:
        MongoDB.client.close()
        logger.info("MongoDB connection closed")

# -------------------------------
# Routes
# -------------------------------

@app.get("/")
def root():
    return {"status": "alive", "message": "ASTA API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

# IMPORTANT → include AFTER defining routes
app.include_router(router, prefix="/api")

# -------------------------------
# Local run (ONLY LOCAL)
# -------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)