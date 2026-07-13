import logging
import asyncio
from fastapi import APIRouter, WebSocket
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.pipeline.task import PipelineTask

from backend.app.auth.token_auth import verify_ws_token_and_device
from backend.app.voice.pipeline import build_pipeline

logger = logging.getLogger("WS_Conversation")
router = APIRouter()

_active_connections: set[WebSocket] = set()

async def broadcast_message(payload: dict):
    """Send a JSON message to every connected WS client (best-effort)."""
    dead = set()
    for ws in list(_active_connections):
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.debug(f"[WS] broadcast_message: dropping dead connection: {e}")
            dead.add(ws)
    _active_connections.difference_update(dead)

@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    trigger = websocket.query_params.get("trigger", "manual")
    if not await verify_ws_token_and_device(websocket):
        await websocket.close(code=1008)
        logger.warning("[WS] Unauthorized connection rejected (invalid token or device)")
        return

    await websocket.accept()
    _active_connections.add(websocket)
    logger.info("[WS] Client connected (authenticated)")

    try:
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
                add_wav_header=True,
                vad_enabled=False # Handled via SileroVADAnalyzer in pipeline
            )
        )
        
        pipeline = build_pipeline(transport, trigger=trigger)
        task = PipelineTask(pipeline)
        
        logger.info("[WS] Starting Pipecat PipelineTask")
        await task.run()

    except Exception as e:
        logger.error(f"[WS] Pipeline error: {e}")
    finally:
        _active_connections.discard(websocket)
        logger.info("[WS] Client disconnected")
