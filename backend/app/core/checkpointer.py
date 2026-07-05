"""
LangGraph checkpointer factory.

Preference order (first reachable wins):
  1. PostgreSQL (AsyncPostgresSaver) — when settings.POSTGRES_URL is set.
  2. MongoDB (MongoDBSaver) — when settings.MONGO_URI is set. Reuses the same
     MongoDB the rest of ASTA already uses, in a dedicated checkpoints DB.
  3. in-memory MemorySaver — so the backend still starts and serves requests
     when neither is available (checkpoints are NOT persisted).
Initialize once at startup via init_checkpointer().
"""
import logging
from typing import Optional

from backend.app.config import settings

logger = logging.getLogger("Checkpointer")

# Dedicated Mongo database for LangGraph checkpoints (kept separate from app data).
MONGO_CHECKPOINT_DB = "asta_checkpoints"

_checkpointer = None
_pg_cm = None      # holds the open AsyncPostgresSaver context manager
_mongo_cm = None   # holds the open MongoDBSaver context manager


async def init_checkpointer():
    """Build the checkpointer once. Postgres > MongoDB > in-memory."""
    global _checkpointer, _pg_cm, _mongo_cm
    if _checkpointer is not None:
        return _checkpointer

    url = (getattr(settings, "POSTGRES_URL", "") or "").strip()
    if url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            _pg_cm = AsyncPostgresSaver.from_conn_string(url)
            saver = await _pg_cm.__aenter__()
            await saver.setup()  # create checkpoint tables if missing
            _checkpointer = saver
            logger.info("Checkpointer: PostgreSQL (AsyncPostgresSaver) ready")
            return _checkpointer
        except Exception as e:
            logger.warning(
                f"Postgres checkpointer unavailable ({e}); trying MongoDB next"
            )
            _pg_cm = None

    mongo_uri = (getattr(settings, "MONGO_URI", "") or "").strip()
    if mongo_uri:
        try:
            from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver
            # AsyncMongoDBSaver (aio module) implements the async
            # (aput/aget_tuple/...) methods ainvoke needs; the sync MongoDBSaver
            # does not, and raises NotImplementedError if used with ainvoke.
            _mongo_cm = AsyncMongoDBSaver.from_conn_string(mongo_uri, db_name=MONGO_CHECKPOINT_DB)
            saver = await _mongo_cm.__aenter__()
            _checkpointer = saver
            logger.info(
                f"Checkpointer: MongoDB (AsyncMongoDBSaver) ready — db '{MONGO_CHECKPOINT_DB}'"
            )
            return _checkpointer
        except Exception as e:
            logger.warning(
                f"MongoDB checkpointer unavailable ({e}); falling back to in-memory MemorySaver"
            )
            _mongo_cm = None

    from langgraph.checkpoint.memory import MemorySaver
    _checkpointer = MemorySaver()
    logger.info("Checkpointer: in-memory (MemorySaver) — checkpoints are not persisted")
    return _checkpointer


def get_checkpointer():
    """Synchronous accessor. Returns a MemorySaver if init hasn't run yet."""
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        _checkpointer = MemorySaver()
    return _checkpointer


async def close_checkpointer():
    """Close the open checkpointer connection on shutdown (no-op for MemorySaver)."""
    global _pg_cm, _mongo_cm
    if _pg_cm is not None:
        try:
            await _pg_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing Postgres checkpointer: {e}")
        finally:
            _pg_cm = None
    if _mongo_cm is not None:
        try:
            await _mongo_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing MongoDB checkpointer: {e}")
        finally:
            _mongo_cm = None
