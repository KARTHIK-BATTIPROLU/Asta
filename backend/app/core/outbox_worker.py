import asyncio
import logging
from backend.app.db.database import db_manager
from backend.app.services.memory.extractor import process_session_extraction

logger = logging.getLogger("OutboxWorker")

_worker_task: asyncio.Task | None = None


async def run_outbox_worker():
    """Background task to process memory extraction asynchronously."""
    logger.info("Starting Outbox Worker...")
    while True:
        try:
            if db_manager.db is not None:
                outbox = db_manager.db["outbox"]
                
                # Find pending extraction task
                task = await outbox.find_one_and_update(
                    {"status": "pending", "kind": "extract"},
                    {"$set": {"status": "processing"}},
                    sort=[("ts", 1)]
                )
                
                if task:
                    session_id = task["payload"]["session_id"]
                    logger.info(f"[Outbox] Processing extraction for session {session_id}")
                    
                    try:
                        await process_session_extraction(session_id)
                        
                        await outbox.update_one(
                            {"_id": task["_id"]},
                            {"$set": {"status": "done"}}
                        )
                        logger.info(f"[Outbox] Successfully extracted session {session_id}")
                    except Exception as e:
                        logger.error(f"[Outbox] Extraction failed for {session_id}: {e}")
                        attempts = task.get("attempts", 0) + 1
                        status = "failed" if attempts >= 3 else "pending"
                        await outbox.update_one(
                            {"_id": task["_id"]},
                            {"$set": {"status": status, "attempts": attempts}}
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
