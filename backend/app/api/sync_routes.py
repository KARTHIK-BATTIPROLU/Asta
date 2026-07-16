from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from backend.app.db.database import db_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class SyncItem(BaseModel):
    client_id: str
    kind: str
    payload: Dict[str, Any]
    created_ts: int

class SyncRequest(BaseModel):
    items: List[SyncItem]

@router.post("/sync")
async def sync_offline_items(req: SyncRequest):
    """
    Idempotent batch sync for offline items from the Android app.
    Conflict rule: server state wins, client edits become new events.
    """
    results = []
    
    for item in req.items:
        try:
            # 1. Deduplication check
            exists = await db_manager.db.offline_sync.find_one({"client_id": item.client_id})
            if exists:
                results.append({"client_id": item.client_id, "status": "ignored", "reason": "already_synced"})
                continue
                
            # 2. Process based on kind
            if item.kind == "capture":
                # Save as a new memory or task
                content = item.payload.get("text", "")
                await db_manager.db.memories.insert_one({
                    "user_id": "karthik",
                    "content": content,
                    "created_at": item.created_ts,
                    "source": "offline_sync"
                })
                logger.info(f"Synced offline capture: {content}")
                
            elif item.kind == "task-complete":
                # Example: Mark reminder as completed
                task_id = item.payload.get("task_id")
                await db_manager.db.reminders.update_one(
                    {"_id": task_id},
                    {"$set": {"state": "completed", "completed_at": item.created_ts}}
                )
                logger.info(f"Synced offline task completion: {task_id}")
            else:
                logger.warning(f"Unknown sync kind: {item.kind}")
                
            # 3. Mark as synced
            await db_manager.db.offline_sync.insert_one({
                "client_id": item.client_id,
                "kind": item.kind,
                "synced_at": item.created_ts
            })
            
            results.append({"client_id": item.client_id, "status": "success"})
            
        except Exception as e:
            logger.error(f"Failed to sync item {item.client_id}: {e}")
            results.append({"client_id": item.client_id, "status": "error", "reason": str(e)})

    return {"results": results}
