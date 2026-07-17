import logging
from datetime import datetime, timezone

from backend.app.db.database import db_manager
from backend.app.voice.session_store import count_user_turns, get_private_flag

logger = logging.getLogger("Outbox")


async def enqueue_extraction(session_id: str) -> bool:
    """
    Enqueue a pending extraction task for a finished session.
    Returns True if a task was enqueued, False if skipped.
    """
    if db_manager.db is None:
        logger.warning("[Outbox] Database not connected; cannot enqueue %s", session_id)
        return False

    user_turns = await count_user_turns(session_id)
    if user_turns < 1:
        logger.info("[Outbox] Session %s has no user turns; skipping enqueue", session_id)
        return False

    private = await get_private_flag(session_id)
    if private in ("no_extract", "no_trace"):
        logger.info("[Outbox] Session %s is private (%s); skipping enqueue", session_id, private)
        return False

    outbox = db_manager.db["outbox"]
    existing = await outbox.find_one({
        "kind": "extract",
        "payload.session_id": session_id,
        "status": "pending",
    })
    if existing:
        logger.info("[Outbox] Pending extract task already exists for session %s", session_id)
        return False

    await outbox.insert_one({
        "kind": "extract",
        "status": "pending",
        "payload": {"session_id": session_id},
        "ts": datetime.now(timezone.utc),
        "attempts": 0,
    })
    logger.info("[Outbox] Enqueued extraction for session %s", session_id)
    return True
