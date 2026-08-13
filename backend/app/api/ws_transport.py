import base64
import logging
import asyncio
import uuid
from fastapi import APIRouter, WebSocket
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
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

async def synthesize_proactive_audio_b64(text: str) -> str | None:
    """Best-effort MP3 TTS for a one-off proactive broadcast (reminders, morning
    brief). Returns base64-encoded MP3 bytes, or None if TTS is unavailable —
    callers must degrade gracefully (broadcast the text without audio)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        from backend.app.services.tts_service import text_to_speech
        audio = await text_to_speech(text)
        return base64.b64encode(audio).decode("utf-8")
    except Exception as e:
        logger.debug(f"[TTS] proactive audio skipped: {e}")
        return None

from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame, TranscriptionFrame, TextFrame
import json

class JsonFrameSerializer(FrameSerializer):
    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            # Pass through audio bytes directly (FastAPIWebsocketTransport handles packetization)
            return frame.audio
        if isinstance(frame, TextFrame):
            return json.dumps({"type": "text", "text": frame.text})
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
        if isinstance(data, str):
            try:
                msg = json.loads(data)
                if msg.get("type") == "text":
                    return TranscriptionFrame(text=msg["text"], user_id="user", timestamp="")
            except:
                pass
        return None

@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    trigger = websocket.query_params.get("trigger", "manual")
    if not await verify_ws_token_and_device(websocket):
        await websocket.close(code=1008)
        logger.warning("[WS] Unauthorized connection rejected (invalid token or device)")
        return

    session_id = str(uuid.uuid4())
    from backend.app.voice.session_store import create_session
    await create_session(session_id)
    logger.info("[WS] Session %s started", session_id)

    await websocket.accept()
    _active_connections.add(websocket)
    logger.info("[WS] Client connected (authenticated)")
    await websocket.send_json({"type": "orb_state", "state": "idle"})

    try:
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
                add_wav_header=True,
                vad_enabled=False, # Handled via SileroVADAnalyzer in pipeline
                serializer=JsonFrameSerializer()
            )
        )
        
        pipeline = build_pipeline(transport, trigger=trigger, session_id=session_id)
        task = PipelineTask(pipeline)

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("[WS] on_client_disconnected fired (session %s)", session_id)
            await task.cancel()

        from pipecat.pipeline.runner import PipelineRunner
        runner = PipelineRunner()
        logger.info("[WS] Starting Pipecat PipelineTask via Runner")
        await runner.run(task)

    except Exception as e:
        logger.error(f"[WS] Pipeline error: {e}")
    finally:
        _active_connections.discard(websocket)
        logger.info("[WS] Client disconnected (session %s)", session_id)
        try:
            from backend.app.services.memory.outbox import enqueue_extraction
            await enqueue_extraction(session_id)
        except Exception as e:
            logger.error("[WS] Failed to enqueue extraction for session %s: %s", session_id, e)
