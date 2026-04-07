import logging
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from typing import Optional
from backend.app.config import config

logger = logging.getLogger("DatabaseManager")

class DatabaseManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
             cls._instance = super(DatabaseManager, cls).__new__(cls)
             cls._instance.mongo_client: Optional[AsyncIOMotorClient] = None
             cls._instance.neo4j_driver = None
        return cls._instance

    async def connect(self):
        """Initializes and binds singleton database pools."""
        # 1. MongoDB Connection
        try:
            mongo_uri = getattr(config, "MONGO_URI", None)
            if not mongo_uri:
                 raise ValueError("MONGO_URI is missing from configurations.")
            self.mongo_client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.mongo_client[config.DB_NAME]
            logger.info("[DatabaseManager] MongoDB cluster bindings initialized.")
        except Exception as e:
            logger.critical(f"[DatabaseManager] Failed to connect to MongoDB: {e}")
            raise e

        # 2. Neo4j Aura Connection
        try:
            neo4j_uri = getattr(config, "NEO4J_URI", None)
            neo_user = getattr(config, "NEO4J_USERNAME", None)
            neo_pass = getattr(config, "NEO4J_PASSWORD", None)
            
            if not all([neo4j_uri, neo_user, neo_pass]):
                logger.warning("[DatabaseManager] Neo4j Aura credentials missing. Skipping Graph Layer.")
            else:
                self.neo4j_driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo_user, neo_pass), connection_timeout=5.0)
                logger.info("[DatabaseManager] Neo4j Aura Graph Database bindings initialized.")
        except Exception as e:
            logger.critical(f"[DatabaseManager] Failed to connect to Neo4j: {e}")
            raise e

    def get_collection(self, collection_name: str):
        if not self.mongo_client:
            raise Exception("Database not connected.")
        return self.db[collection_name]

    async def ping(self) -> bool:
        """Executes startup life-cycle sanity checks mapped to explicit exception traces."""
        health = True
        
        # Ping Mongo
        if self.mongo_client:
            try:
                await self.mongo_client.admin.command('ping')
                logger.info("✔️  MongoDB Health Check: Passed")
            except Exception as e:
                logger.error(f"❌ MongoDB Network Timeout or Auth Failure: {e}")
                health = False
        
        # Ping Neo4j
        if self.neo4j_driver:
            try:
                await self.neo4j_driver.verify_connectivity()
                logger.info("✔️  Neo4j Aura Health Check: Passed")
            except Exception as e:
                logger.error(f"❌ Neo4j Authentication Error or Instance Unavailable: {e}")
                health = False
                
        return health

    async def disconnect(self):
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("[DatabaseManager] MongoDB bounds closed safely.")
        if self.neo4j_driver:
            await self.neo4j_driver.close()
            logger.info("[DatabaseManager] Neo4j bindings shutdown successfully.")
            
db_manager = DatabaseManager()
