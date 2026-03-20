from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routes import router
from backend.app.config import config
from backend.app.db.mongo import MongoDB
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ASTA API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to DB on startup
@app.on_event("startup")
def startup_db_client():
    config.validate()
    MongoDB.connect()
    logger.info("Connected to MongoDB")

@app.on_event("shutdown")
def shutdown_db_client():
    if MongoDB.client:
        MongoDB.client.close()
        logger.info("Closed MongoDB connection")

# Health Check
@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "ASTA API"}

# Include Routes
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting ASTA API server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)