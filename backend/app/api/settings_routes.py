from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import logging
from backend.app.core.registry import registry
from backend.app.auth.token_auth import verify_bearer_and_device

router = APIRouter()
logger = logging.getLogger("SettingsRoutes")

class SilentModePayload(BaseModel):
    silent_mode: bool
    session_id: str

@router.post("/settings/silent")
async def toggle_silent_mode(
    payload: SilentModePayload,
    _=Depends(verify_bearer_and_device)
):
    """
    Sets the silent mode flag for a session/identity in Redis.
    """
    try:
        redis_pool = registry.get("redis")
        if not redis_pool:
            logger.warning("[Settings] Redis not configured")
            return {"status": "error", "message": "Redis not configured"}

        await redis_pool.set(f"asta:settings:silent_mode:{payload.session_id}", str(payload.silent_mode).lower())
        logger.info(f"[Settings] Silent mode set to {payload.silent_mode} for session {payload.session_id}")
        
        if not payload.silent_mode:
            digest_key = f"asta:settings:silent_digest:{payload.session_id}"
            length = await redis_pool.llen(digest_key)
            if length > 0:
                items = await redis_pool.lrange(digest_key, 0, -1)
                await redis_pool.delete(digest_key)
                
                import asyncio
                from backend.app.api.ws_transport import broadcast_message, synthesize_proactive_audio_b64
                
                async def send_digest():
                    items_str = "\n".join([i.decode('utf-8') if isinstance(i, bytes) else i for i in items])
                    digest_msg = f"Boss, while you were on silent mode, here's what you missed:\n{items_str}"
                    # temporarily bypass silent mode for this specific synthesis
                    # Actually synthesize_proactive_audio_b64 will see silent_mode=false now.
                    try:
                        from backend.app.services.tts_service import text_to_speech
                        import base64
                        audio_b64 = None
                        try:
                            audio = await text_to_speech(digest_msg)
                            audio_b64 = base64.b64encode(audio).decode("utf-8")
                        except Exception as e:
                            logger.error(f"[Settings] Failed to synthesize digest: {e}")
                        
                        await broadcast_message({
                            "type": "asta_proactive",
                            "trigger": "silent_mode_off",
                            "response": digest_msg,
                            "audio_base64": audio_b64
                        })
                    except Exception as e:
                        logger.error(f"[Settings] Failed to broadcast digest: {e}")
                        
                asyncio.create_task(send_digest())
                
        return {"status": "success", "silent_mode": payload.silent_mode}
    except Exception as e:
        logger.error(f"[Settings] Error setting silent mode: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def is_silent_mode(session_id: str) -> bool:
    """Helper for internal backend checks."""
    redis_pool = registry.get("redis")
    if not redis_pool:
        return False
    val = await redis_pool.get(f"asta:settings:silent_mode:{session_id}")
    return val == b"true" or val == "true"
