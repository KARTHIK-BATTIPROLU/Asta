import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.db.database import db_manager

logger = logging.getLogger("SessionStore")

STALE_SESSION_MINUTES = 15


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


async def sweep_stale_sessions() -> int:
    """Close voice sessions that never got a clean WS disconnect (crashed
    process, dropped network) and enqueue them for extraction. Safety net
    for the normal on_client_disconnected path in ws_transport.py.

    Scoped to documents with a `turns` field (this schema) to avoid
    touching the legacy `messages`/`workflow_type` session docs that share
    this collection.
    """
    if db_manager.db is None:
        return 0

    from backend.app.services.memory.outbox import enqueue_extraction

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_SESSION_MINUTES)
    sessions = db_manager.db["sessions"]
    swept = 0
    cursor = sessions.find({
        "status": "active",
        "turns": {"$exists": True},
        "$or": [
            {"updated_at": {"$lt": cutoff}},
            {"updated_at": {"$exists": False}, "started_at": {"$lt": cutoff}},
        ],
    })
    async for doc in cursor:
        session_id = doc["session_id"]
        await sessions.update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc), "closed_by": "sweeper"}},
        )
        await enqueue_extraction(session_id)
        swept += 1
    if swept:
        logger.warning("[SessionStore] Sweeper closed %s stale session(s)", swept)
    return swept
