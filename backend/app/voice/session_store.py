import logging
from datetime import datetime, timezone
from typing import Optional

from backend.app.db.database import db_manager

logger = logging.getLogger("SessionStore")


async def create_session(session_id: str) -> bool:
    """Create a new voice session document in Mongo."""
    if db_manager.db is None:
        logger.warning("[SessionStore] Database not connected; cannot create session %s", session_id)
        return False

    now = datetime.now(timezone.utc)
    await db_manager.db["sessions"].insert_one({
        "session_id": session_id,
        "turns": [],
        "started_at": now,
        "status": "active",
    })
    logger.info("[SessionStore] Created session %s", session_id)
    return True


async def append_turn(session_id: str, role: str, text: str) -> bool:
    """Append a turn to the session transcript."""
    if db_manager.db is None:
        return False

    text = (text or "").strip()
    if not text:
        return False

    now = datetime.now(timezone.utc)
    result = await db_manager.db["sessions"].update_one(
        {"session_id": session_id},
        {
            "$push": {"turns": {"role": role, "text": text, "ts": now}},
            "$set": {"updated_at": now},
        },
    )
    return result.matched_count > 0


async def count_user_turns(session_id: str) -> int:
    """Count user turns in a session (for outbox enqueue guard)."""
    if db_manager.db is None:
        return 0

    session = await db_manager.db["sessions"].find_one(
        {"session_id": session_id},
        {"turns": 1},
    )
    if not session:
        return 0

    turns = session.get("turns", [])
    return sum(1 for t in turns if t.get("role") == "user")


async def get_private_flag(session_id: str) -> Optional[str]:
    """Return the session private flag, if set."""
    if db_manager.db is None:
        return None

    session = await db_manager.db["sessions"].find_one(
        {"session_id": session_id},
        {"private": 1},
    )
    if not session:
        return None
    return session.get("private")


async def set_private(session_id: str, flag: str = "no_extract") -> bool:
    """Mark session as private (skip extraction)."""
    if db_manager.db is None:
        return False

    result = await db_manager.db["sessions"].update_one(
        {"session_id": session_id},
        {"$set": {"private": flag}},
    )
    return result.matched_count > 0


async def clear_private(session_id: str) -> bool:
    """Clear private flag from session."""
    if db_manager.db is None:
        return False

    result = await db_manager.db["sessions"].update_one(
        {"session_id": session_id},
        {"$unset": {"private": ""}},
    )
    return result.matched_count > 0
