"""
ASTA HTTP API routes.

All MongoDB operations delegated to db_manager. No direct PyMongo imports.
"""

import os
import hmac
import logging
import base64
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from backend.app.db.database import db_manager
from backend.app.services.llm_service import stream_llm_response
from backend.app.services.tts_service import text_to_speech
from backend.app.core.circuit_breaker import status_registry
from backend.app.api.turn_processor import fetch_memory_context
from backend.app.services.l1_cache import l1_manager
from backend.app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    voice_enabled: bool = False
    session_id: str | None = None
    workflow_hint: str | None = None  # Optional workflow hint for supervisor


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    audio_base64: str | None = None


@router.get("/health")
async def health_check():
    """Enhanced health check with circuit breaker status and memory tier health."""
    mongo_status = "connected" if (db_manager.mongo_client and not db_manager.degraded_mode) else "disconnected"

    # Get circuit breaker and memory tier health
    health_report = status_registry.get_all_health()
    memory_mode = status_registry.get_memory_mode()
    status_summary = status_registry.get_status_summary()

    return {
        "status": "ok" if mongo_status == "connected" else "degraded",
        "timestamp": time.time(),
        "database": mongo_status,
        "memory_mode": memory_mode,
        "services": status_summary,
        "circuit_breakers": {
            "l2_vector": health_report.get("circuit_l2_vector", {}),
            "l3_graph": health_report.get("circuit_l3_graph", {}),
        },
        "tools": _get_tool_status(),
    }


def _get_tool_status() -> dict:
    """Get registered tool names for health check."""
    try:
        from backend.app.tools.tool_registry import tool_registry
        return {"registered": tool_registry.tool_names, "count": len(tool_registry.tool_names)}
    except Exception:
        return {"registered": [], "count": 0}


@router.get("/health/circuits")
def circuit_status():
    """Detailed circuit breaker status endpoint for monitoring."""
    return status_registry.get_all_health()


from backend.app.auth.token_auth import verify_bearer, verify_bearer_and_device
from datetime import datetime, timezone

verify_token = verify_bearer_and_device

@router.post("/device/register")
async def register_device(payload: dict, token: str = Depends(verify_bearer)):
    device_id = payload.get("device_id")
    device_name = payload.get("device_name", "Unknown Android Device")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")
    
    collection = db_manager.get_collection("registered_devices")
    existing = await collection.find_one({})
    if existing:
        if existing["device_id"] != device_id:
            raise HTTPException(
                status_code=403, 
                detail="Another device is already registered. Single device policy is enforced."
            )
        # Device is already registered; update last seen and name
        await collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {"device_name": device_name, "last_seen": datetime.now(timezone.utc)}}
        )
    else:
        # Register new device
        await collection.insert_one({
            "device_id": device_id,
            "device_name": device_name,
            "registered_at": datetime.now(timezone.utc),
            "last_seen": datetime.now(timezone.utc)
        })
    return {"status": "success", "message": f"Device {device_id} registered successfully."}


@router.post("/admin/reset/circuit/{circuit_name}")
def reset_circuit(circuit_name: str, token: str = Depends(verify_token)):
    """Manually force a circuit breaker to close."""
    logger.info(f"Manual override: Resetting circuit {circuit_name}")
    circuit = status_registry.get_circuit_breaker(circuit_name)
    if circuit:
        circuit.force_close()
        return {"status": "success", "message": f"Circuit {circuit_name} manually reset (force closed)"}
    return {"status": "error", "message": f"Circuit {circuit_name} not found"}


@router.post("/chat", response_model=ChatResponse)
async def handle_chat(req: ChatRequest, token: str = Depends(verify_token)):
    logger.info(f"POST /api/chat received text: {req.message}")

    full_reply = ""
    session_id = req.session_id or str(uuid.uuid4())
    try:
        # Use the supervisor LangGraph for orchestration
        from backend.app.core.supervisor_graph import run_supervisor_graph

        # Fetch L1 session history only (skip RAG — the supervisor graph's
        # other_workflow decides per-turn whether to search long-term memory).
        history = []
        try:
            history, _ = await fetch_memory_context(req.message, session_id, skip_rag=True)
        except Exception as mem_err:
            logger.error(f"[Chat] Error fetching history: {mem_err}")

        # Run supervisor graph (classifies intent + routes + checkpoints)
        result = await run_supervisor_graph(
            session_id=session_id,
            user_input=req.message,
            messages=history or [],
        )

        full_reply = result.get("response", "")

        # Save to session
        if full_reply.strip():
            try:
                await SessionManager.add_message(session_id, "user", req.message)
                await SessionManager.add_message(session_id, "assistant", full_reply.strip())
            except Exception as e:
                logger.error(f"POST /api/chat Error saving messages to SessionManager: {e}")

    except Exception as e:
        logger.error(f"Error during supervisor execution in handle_chat: {e}")
        full_reply = "I'm sorry, I encountered an error answering your text."
    
    audio_base64 = None
    if req.voice_enabled and full_reply.strip():
        try:
            tts_audio = await text_to_speech(full_reply.strip())
            if tts_audio:
                audio_base64 = base64.b64encode(tts_audio).decode("utf-8")
        except Exception as e:
            logger.error(f"TTS stream error in handle_chat: {e}")

    logger.info(f"POST /api/chat returning reply length: {len(full_reply)}, audio included: {audio_base64 is not None}")
    logger.debug(f"POST /api/chat full reply text: {full_reply}")

    return ChatResponse(session_id=session_id, reply=full_reply, audio_base64=audio_base64)


class DeviceTokenRequest(BaseModel):
    device_id: str
    fcm_token: str


@router.post("/device-token")
async def register_device_token(req: DeviceTokenRequest, token: str = Depends(verify_token)):
    """Register or refresh an FCM device token for push notifications.

    The Android app calls this on every launch after receiving a (possibly
    rotated) token from FirebaseMessagingService.onNewToken().  Upserts by
    device_id so a single device never accumulates stale tokens.
    """
    try:
        from backend.app.db.database import db_manager
        db = db_manager.db
        await db["device_tokens"].update_one(
            {"device_id": req.device_id},
            {"$set": {"device_id": req.device_id, "token": req.fcm_token}},
            upsert=True,
        )
        logger.info(f"[device-token] registered/refreshed token for device {req.device_id[:8]}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[device-token] {e}")
        raise HTTPException(status_code=500, detail="Failed to store device token")


@router.post("/trigger/morning-brief")
async def trigger_morning_brief(token: str = Depends(verify_token)):
    """Manually fire the morning brief through the supervisor graph (same
    input the 5:30 AM scheduler callback uses), broadcasting the result (with
    spoken audio, best-effort) to any open WS clients."""
    from backend.app.core.supervisor_graph import run_supervisor_graph
    from backend.app.api.ws_transport import broadcast_message, synthesize_proactive_audio_b64

    session_id = f"alarm-manual-{uuid.uuid4().hex[:8]}"
    result = await run_supervisor_graph(
        session_id=session_id,
        user_input="morning alarm triggered, give me my morning brief",
    )
    response_text = result.get("response", "")

    audio_b64 = await synthesize_proactive_audio_b64(response_text) if response_text else None
    try:
        payload = {
            "type": "asta_proactive",
            "trigger": "morning_alarm",
            "response": response_text,
        }
        if audio_b64:
            payload["audio_base64"] = audio_b64
        await broadcast_message(payload)
    except Exception as e:
        logger.error(f"[trigger_morning_brief] broadcast failed: {e}")

    return {"session_id": session_id, "response": response_text, "audio_included": audio_b64 is not None}


class SyncItem(BaseModel):
    id: str
    type: str  # 'research', 'reminder', 'other'
    payload_json: str  # structured payload or raw text
    created_at: int | float


class SyncBatchRequest(BaseModel):
    items: list[SyncItem]


@router.post("/sync/batch")
async def sync_batch(req: SyncBatchRequest, token: str = Depends(verify_token)):
    """Process a batch of queued offline interactions."""
    from backend.app.core.supervisor_graph import run_supervisor_graph
    
    results = []
    processed_count = 0
    
    for item in req.items:
        session_id = f"offline-{uuid.uuid4().hex[:8]}"
        try:
            if item.type in ("research", "reminder"):
                user_input = f"Offline Sync Request [{item.type.upper()}]: {item.payload_json}. Please process this offline request and acknowledge."
            else:
                user_input = f"Offline Sync Note: {item.payload_json}. Please save this."
                
            res = await run_supervisor_graph(
                session_id=session_id,
                user_input=user_input
            )
            
            results.append({"id": item.id, "status": "synced", "reply": res.get("response", "")})
            processed_count += 1
            
        except Exception as e:
            logger.error(f"[Sync] Error processing offline item {item.id}: {e}")
            results.append({"id": item.id, "status": "failed", "error": str(e)})

    if processed_count > 0:
        try:
            from backend.app.api.ws_transport import broadcast_message, synthesize_proactive_audio_b64
            summary_msg = f"Boss, I've caught up on {processed_count} items from your offline queue."
            audio_b64 = await synthesize_proactive_audio_b64(summary_msg)
            
            payload = {
                "type": "asta_proactive",
                "trigger": "offline_sync",
                "response": summary_msg
            }
            if audio_b64:
                payload["audio_base64"] = audio_b64
                
            await broadcast_message(payload)
        except Exception as e:
            logger.error(f"[Sync] Broadcast failed: {e}")

    return {"status": "ok", "processed": processed_count, "results": results}


class AppUsage(BaseModel):
    package_name: str
    minutes: int

class DailyMetricsPayload(BaseModel):
    dateIso: str
    topApps: list[AppUsage]
    totalScreenTimeMinutes: int
    stepCount: int
    sleepMinutes: int


@router.post("/metrics/daily")
async def post_daily_metrics(payload: DailyMetricsPayload, token: str = Depends(verify_token)):
    """Ingest digital wellbeing snapshot from Android app."""
    try:
        from backend.app.db.database import db_manager
        db = db_manager.db
        collection = db["wellbeing"]
        
        doc = payload.model_dump()
        doc["recorded_at"] = datetime.now(timezone.utc)
        
        await collection.insert_one(doc)
        
        # Update rolling aggregates in Neo4j
        try:
            from backend.app.core.registry import registry
            db_manager = registry.get("db")
            if db_manager and hasattr(db_manager, "neo4j_driver"):
                async with db_manager.neo4j_driver.session() as session:
                    query = """
                    MATCH (u:Identity {name: 'KARTHIK'})
                    CREATE (m:DailyMetrics {
                        date: $date,
                        screen_time_minutes: $st,
                        step_count: $steps,
                        sleep_minutes: $sleep,
                        recorded_at: datetime()
                    })
                    CREATE (u)-[:RECORDED_ON]->(m)
                    WITH u
                    MATCH (u)-[:RECORDED_ON]->(recent:DailyMetrics)
                    WITH u, recent ORDER BY recent.recorded_at DESC LIMIT 7
                    WITH u, 
                         avg(recent.sleep_minutes) AS avg_sleep_7d, 
                         avg(recent.step_count) AS avg_steps_7d,
                         avg(recent.screen_time_minutes) AS avg_screen_time_7d
                    SET u.avg_sleep_7d = avg_sleep_7d,
                        u.avg_steps_7d = avg_steps_7d,
                        u.avg_screen_time_7d = avg_screen_time_7d
                    """
                    await session.run(query, date=payload.dateIso, st=payload.totalScreenTimeMinutes, steps=payload.stepCount, sleep=payload.sleepMinutes)
                    logger.info("[Metrics] Neo4j wellbeing aggregates updated")
        except Exception as neo_err:
            logger.error(f"[Metrics] Failed to update Neo4j aggregates: {neo_err}")
            
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[Metrics] Failed to store metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to store metrics")
