# ASTA Database Validation Config
# Using Pydantic Settings for Type Checking and Validation

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import logging

logger = logging.getLogger(__name__)

class DatabaseSettings(BaseSettings):
    # MongoDB 
    MONGO_URI: str = Field(..., description="MongoDB Atlas Connection URI")
    
    # Neo4j Aura
    NEO4J_URI: str = Field(..., description="Neo4j Aura database routing string")
    NEO4J_USERNAME: str = Field(..., description="Neo4j Aura database username")
    NEO4J_PASSWORD: str = Field(..., description="Neo4j Aura database password")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

try:
    db_settings = DatabaseSettings()
except Exception as e:
    logger.critical(f"Database Environment Validation Failed: {e}")
    # Soft fallback to empty structures so Uvicorn can still boot to gracefully print the error ping layer.
    db_settings = None
