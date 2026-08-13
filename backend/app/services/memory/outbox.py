import logging
from datetime import datetime, timedelta, timezone

from backend.app.db.database import db_manager
from backend.app.voice.session_store import count_user_turns, get_private_flag

logger = logging.getLogger("Outbox")

STALE_PROCESSING_MINUTES = 10


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

    now = datetime.now(timezone.utc)
    await outbox.insert_one({
        "kind": "extract",
        "status": "pending",
        "payload": {"session_id": session_id},
        "ts": now,
        "updated_at": now,
        "attempts": 0,
    })
    logger.info("[Outbox] Enqueued extraction for session %s", session_id)
    return True


async def reclaim_stale_outbox_tasks() -> int:
    """Reset outbox tasks stuck in 'processing' back to 'pending' (respecting
    the 3-strikes -> failed limit). Recovers tasks orphaned by a worker
    process that died mid-extraction, since nothing else ever revisits them.
    """
    if db_manager.db is None:
        return 0

    outbox = db_manager.db["outbox"]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_PROCESSING_MINUTES)
    reclaimed = 0
    async for task in outbox.find({"status": "processing", "updated_at": {"$lt": cutoff}}):
        attempts = task.get("attempts", 0) + 1
        status = "failed" if attempts >= 3 else "pending"
        await outbox.update_one(
            {"_id": task["_id"]},
            {"$set": {"status": status, "attempts": attempts, "updated_at": datetime.now(timezone.utc)}},
        )
        reclaimed += 1
        logger.warning(
            "[Outbox] Reclaimed stale processing task %s -> %s (attempts=%s)",
            task["_id"], status, attempts,
        )
    return reclaimed
