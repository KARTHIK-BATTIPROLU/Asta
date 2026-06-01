"""
Session persistence helpers.

Delegates all MongoDB operations to the unified db_manager.
No standalone Motor/PyMongo clients.
"""

import logging
from datetime import datetime, timezone
from backend.app.db.database import db_manager

logger = logging.getLogger(__name__)


async def save_message(session_id: str, user_text: str, asta_text: str):
    """Append a user/assistant message pair to the session document."""
    try:
        collection = db_manager.get_collection("sessions")
        await collection.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "messages": {
                        "user": user_text,
                        "asta": asta_text,
                        "timestamp": datetime.now(timezone.utc),
                    }
                },
                "$setOnInsert": {
                    "session_id": session_id,
                    "created": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )
    except Exception as e:
        logger.error(f"[session.save_message] Failed: {e}")


async def get_history(session_id: str, limit: int = 10) -> list:
    """Return last N messages in OpenAI format for LLM context."""
    try:
        collection = db_manager.get_collection("sessions")
        doc = await collection.find_one({"session_id": session_id})
        if not doc:
            return []

        messages = doc.get("messages", [])[-limit:]
        formatted = []
        for m in messages:
            formatted.append({"role": "user", "content": m.get("user", "")})
            formatted.append({"role": "assistant", "content": m.get("asta", "")})
        return formatted
    except Exception as e:
        logger.error(f"[session.get_history] Failed: {e}")
        return []
