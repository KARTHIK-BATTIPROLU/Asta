from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.config import config as settings
from datetime import datetime

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client["asta"]

async def save_message(session_id: str, user_text: str, asta_text: str):
    await db.sessions.update_one(
        {"session_id": session_id},
        {
            "$push": {
                "messages": {
                    "user": user_text,
                    "asta": asta_text,
                    "timestamp": datetime.utcnow(),
                }
            },
            "$setOnInsert": {"session_id": session_id, "created": datetime.utcnow()},
        },
        upsert=True,
    )

async def get_history(session_id: str, limit: int = 10) -> list:
    """Return last N messages in OpenAI format for LLM context."""
    doc = await db.sessions.find_one({"session_id": session_id})
    if not doc:
        return []
    
    messages = doc.get("messages", [])[-limit:]
    formatted = []
    for m in messages:
        formatted.append({"role": "user", "content": m["user"]})
        formatted.append({"role": "assistant", "content": m["asta"]})
    return formatted
