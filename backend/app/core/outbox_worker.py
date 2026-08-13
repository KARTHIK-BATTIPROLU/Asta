import asyncio
import logging
from datetime import datetime, timedelta, timezone
from backend.app.db.database import db_manager
from backend.app.services.memory.extractor import process_session_extraction
from backend.app.services.memory.outbox import reclaim_stale_outbox_tasks, STALE_PROCESSING_MINUTES

logger = logging.getLogger("OutboxWorker")

_worker_task: asyncio.Task | None = None


async def run_outbox_worker():
    """Background task to process memory extraction asynchronously."""
    logger.info("Starting Outbox Worker...")
    last_reclaim_check = None
    while True:
        try:
            if db_manager.db is not None:
                now = datetime.now(timezone.utc)
                if last_reclaim_check is None or (now - last_reclaim_check) >= timedelta(minutes=STALE_PROCESSING_MINUTES):
                    last_reclaim_check = now
                    reclaimed = await reclaim_stale_outbox_tasks()
                    if reclaimed:
                        logger.warning(f"[Outbox] Reclaimed {reclaimed} stale processing task(s) on startup/periodic check")

                outbox = db_manager.db["outbox"]

                # Find pending extraction task
                task = await outbox.find_one_and_update(
                    {"status": "pending", "kind": "extract"},
                    {"$set": {"status": "processing", "updated_at": now}},
                    sort=[("ts", 1)]
                )

                if task:
                    session_id = task["payload"]["session_id"]
                    logger.info(f"[Outbox] Processing extraction for session {session_id}")

                    try:
                        await process_session_extraction(session_id)

                        await outbox.update_one(
                            {"_id": task["_id"]},
                            {"$set": {"status": "done", "updated_at": datetime.now(timezone.utc)}}
                        )
                        logger.info(f"[Outbox] Successfully extracted session {session_id}")
                    except Exception as e:
                        logger.error(f"[Outbox] Extraction failed for {session_id}: {e}")
                        attempts = task.get("attempts", 0) + 1
                        status = "failed" if attempts >= 3 else "pending"
                        await outbox.update_one(
                            {"_id": task["_id"]},
                            {"$set": {"status": status, "attempts": attempts, "updated_at": datetime.now(timezone.utc)}}
                        )
                else:
                    # Nothing to process, sleep
                    await asyncio.sleep(5)
            else:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("[Outbox] Worker cancelled")
            raise
        except Exception as e:
            logger.error(f"[Outbox] Worker error: {e}")
            await asyncio.sleep(5)


def start_outbox_worker():
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        logger.info("[Outbox] Worker already running")
        return
    _worker_task = asyncio.create_task(run_outbox_worker())


async def stop_outbox_worker():
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
    logger.info("[Outbox] Worker stopped")
