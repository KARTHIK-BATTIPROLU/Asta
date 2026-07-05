import os
import hmac
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.services.stt_service import transcribe_audio
from backend.app.services.llm_service import stream_llm_response
from backend.app.services.tts_service import synthesize_speech_stream
from backend.app.services.wake_word_service import get_wake_word_service
from backend.app.db.session import save_message, get_history
from backend.app.db.memory_handler import memory_handler
from backend.app.core.registry import safe_get, registry
from backend.app.services.l1_cache import l1_manager
from backend.app.core.circuit_breaker import status_registry
from backend.app.speech.deepgram_stream import DeepgramStreamService
from memory.l2_graph import l2_graph
from backend.app.services.llm_hardening import sanitize_input
from backend.app.auth.token_auth import verify_ws_token_and_device
from backend.app.models.action_model import ActionRequest
from backend.app.core.turn_state import TurnStateMachine, TurnState
from backend.app.core.task_registry import TaskRegistry
import json, asyncio, logging, re, struct, uuid, base64

logger = logging.getLogger("WS_Conversation")

router = APIRouter()



# ── Proactive broadcast (reminders, alarms, etc.) ───────────────────────────
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

from backend.app.api.turn_processor import TurnContext, TurnProcessor, broadcast_error
@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    if not await verify_ws_token_and_device(websocket):
        await websocket.close(code=1008)
        logger.warning("[WS] Unauthorized connection rejected (invalid token or device)")
        return

    await websocket.accept()
    _active_connections.add(websocket)
    logger.info("[WS] Client connected (authenticated)")
    session_id = None
    audio_buffer = bytearray()
    tsm = None
    
    # Wake word detection state
    wake_word_service = get_wake_word_service()
    wake_word_mode = False  # When True, only listen for wake word
    wake_word_detected = False
    
    session_context = {
        "turn_task": None,
        "tts_worker_task": None
    }
    
    redis_pool = registry.get("redis")
    client_active = True
    
    # L1.5 Speculative Streamer context
    stt_stream = None
    stt_stream_ready = False
    stt_listener_task = None
    stt_connect_task = None
    last_prefetch_time = 0.0
    
    # Wake word detection callback
    async def on_wake_word_detected(wake_word: str, confidence: float):
        nonlocal wake_word_detected, wake_word_mode
        logger.info(f"[WakeWord] '{wake_word}' detected with confidence {confidence:.3f}")
        wake_word_detected = True
        wake_word_mode = False  # Exit wake word mode, start listening
        
        try:
            if client_active:
                await websocket.send_json({
                    "type": "wake_word_detected",
                    "wake_word": wake_word,
                    "confidence": confidence,
                    "message": "Wake word detected! Listening..."
                })
                await websocket.send_json({"type": "status", "status": "listening"})
        except Exception as e:
            logger.error(f"[WakeWord] Failed to send detection notification: {e}")
    
    # Set wake word callback if service is available
    if wake_word_service and wake_word_service.is_ready():
        wake_word_service.set_detection_callback(on_wake_word_detected)
        logger.info("[WakeWord] Service ready and callback set")

    async def start_stt_stream():
        nonlocal stt_stream, stt_listener_task, last_prefetch_time, stt_stream_ready
        if isinstance(stt_stream, DeepgramStreamService):
            return

        local_stream = DeepgramStreamService()
        success = await local_stream.start(sample_rate=16000) # Ensure client sample rate matches
        
        if success:
            if not client_active or not accepting_audio:
                logger.info("[STT L1.5] Turn ended before STT stream connected. Closing zombie stream.")
                await local_stream.stop()
                stt_stream = None
                stt_stream_ready = False
                return

            stt_stream = local_stream
            stt_stream_ready = True
            # Flush the entire buffer accumulated during connection
            if audio_buffer:
                await local_stream.send_audio(bytes(audio_buffer))
        else:
            logger.warning("[STT L1.5] Failed to start streaming STT fallback")
            stt_stream = None
            stt_stream_ready = False
            return

        async def keep_alive_loop(stream):
            while client_active and stream.is_stream_active:
                await asyncio.sleep(8)
                try:
                    if stream.connection and hasattr(stream.connection, "keep_alive"):
                        stream.connection.keep_alive()
                except Exception as e:
                    logger.debug(f"[STT L1.5] Keep-alive failed: {e}")

        async def stt_event_listener(stream):
            nonlocal last_prefetch_time
            try:
                while client_active and stream.is_stream_active:
                    try:
                        event = await asyncio.wait_for(stream.get_transcript(), timeout=5.0)
                    except asyncio.TimeoutError:
                        # Keep-alive to prevent 1011 timeout
                        if stream.connection and hasattr(stream.connection, "keep_alive"):
                            try:
                                stream.connection.keep_alive()
                            except Exception as e:
                                logger.debug(f"[STT L1.5] KeepAlive failed: {e}")
                        continue # Prevents deadlocks if upstream is silent

                    if event.get("type") == "transcript":
                        text = event.get("text", "").strip()
                        is_final = event.get("is_final", False)
                        words = text.split()
                        
                        if not is_final and len(words) > 1 and session_id:
                            now = asyncio.get_event_loop().time()
                            if now - last_prefetch_time > 1.5:  # 1.5s debounce
                                # KEYWORD FILTER: Only prefetch if transcript contains entity
                                try:
                                    entity_names = await l2_graph.get_all_entity_names()
                                    text_lower = text.lower()
                                    keyword_match = any(name.lower() in text_lower for name in entity_names)
                                    
                                    if keyword_match:
                                        last_prefetch_time = now
                                        import backend.app.services.memory_orchestrator as mo
                                        TaskRegistry.track(
                                            mo.orchestrator.speculative_prefetch(text, session_id),
                                            name=f"speculative_prefetch:{session_id[:8]}",
                                            session_id=session_id,
                                        )
                                        logger.info(f"[STT L1.5] Keyword match triggered prefetch: '{text[:50]}...'")
                                except Exception as kw_err:
                                    logger.debug(f"[STT L1.5] Keyword filter check failed: {kw_err}")
                                
                        if is_final and text:
                            # We can also push it as final transcript if needed, but we gather it at finish()
                            pass
            except Exception as e:
                logger.debug(f"[STT L1.5] Background listener closed: {e}")

        stt_listener_task = asyncio.create_task(stt_event_listener(stt_stream))
        asyncio.create_task(keep_alive_loop(stt_stream))
        
    ctx = TurnContext(websocket, registry.get("redis"))
    turn_processor = TurnProcessor(ctx)
    accepting_audio = True

    try:
        while ctx.client_active:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                logger.info("[WS] Client disconnected natively")
                break
            except RuntimeError as e:
                # Catch RuntimeError when socket drops mid receive
                logger.info(f"[WS] Client disconnected with RuntimeError: {e}")
                break

            if "bytes" in message:
                if accepting_audio:
                    # Wake word detection mode
                    if wake_word_mode and wake_word_service and wake_word_service.is_ready():
                        # Process audio for wake word detection
                        detection = await wake_word_service.process_audio_stream(message["bytes"])
                        if detection:
                            # Wake word detected, callback will handle state transition
                            audio_buffer = bytearray()  # Clear buffer
                            continue
                        # Don't accumulate audio in wake word mode
                        continue
                    
                    # Normal audio processing
                    audio_buffer.extend(message["bytes"])
                    # Send bytes to streaming engine if active
                    if not ctx.stt_stream:
                        ctx.stt_stream = True # Lock to prevent multiple creations immediately
                        ctx.stt_connect_task = asyncio.create_task(start_ctx.stt_stream())
                    elif ctx.ctx.stt_stream_ready and isinstance(ctx.stt_stream, DeepgramStreamService):
                        asyncio.create_task(ctx.stt_stream.send_audio(message["bytes"]))

            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    if ctx.client_active:
                        await websocket.send_json({"type": "error", "message": "Invalid JSON control message"})
                    continue

                msg_type = data.get("type")
                logger.info(f"[WS] Control message: {msg_type}")

                if msg_type == "session_start":
                    session_id = data.get("session_id")
                    # Check if wake word mode should be enabled
                    wake_word_mode = data.get("wake_word_mode", False)
                    
                    if session_id and redis_pool:
                        try:
                            exists = await redis_pool.exists(f"asta:session:{session_id}")
                            if not exists:
                                await redis_pool.hset(f"asta:session:{session_id}", "sequence_id", 0)
                                await redis_pool.hset(f"asta:session:{session_id}", "is_interrupted", "false")
                                await redis_pool.hset(f"asta:session:{session_id}", "current_turn_id", "")
                                await redis_pool.expire(f"asta:session:{session_id}", 1800)
                        except Exception as e:
                            logger.error(f"[WS] Redis error during session_start: {e}")
                    
                    if ctx.client_active:
                        response = {"type": "ready"}
                        if wake_word_service and wake_word_service.is_ready():
                            response["wake_word_enabled"] = True
                            response["wake_word_models"] = wake_word_service.get_available_models()
                        await websocket.send_json(response)
                        
                        if wake_word_mode:
                            await websocket.send_json({
                                "type": "status",
                                "status": "wake_word_listening",
                                "message": "Waiting for wake word..."
                            })

                elif msg_type == "enable_wake_word":
                    # Enable wake word detection mode
                    if wake_word_service and wake_word_service.is_ready():
                        wake_word_mode = True
                        wake_word_detected = False
                        audio_buffer = bytearray()
                        logger.info("[WakeWord] Wake word mode enabled")
                        if ctx.client_active:
                            await websocket.send_json({
                                "type": "wake_word_mode",
                                "enabled": True,
                                "message": "Say the wake word to activate"
                            })
                    else:
                        if ctx.client_active:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Wake word detection not available"
                            })
                
                elif msg_type == "disable_wake_word":
                    # Disable wake word detection mode
                    wake_word_mode = False
                    logger.info("[WakeWord] Wake word mode disabled")
                    if ctx.client_active:
                        await websocket.send_json({
                            "type": "wake_word_mode",
                            "enabled": False
                        })

                elif msg_type == "trigger":
                    trigger_name = data.get("name")
                    logger.info(f"[WS] Hardware Trigger received: {trigger_name}")
                    
                    if trigger_name == "morning_alarm":
                        # Bypass STT and force a morning routine trigger turn
                        lat = data.get("lat")
                        lon = data.get("lon")
                        override_text = f"[MORNING ALARM TRIGGER] lat: {lat}, lon: {lon}" if (lat and lon) else "[MORNING ALARM TRIGGER]"
                        
                        audio_buffer = bytearray()
                        if ctx.session_context["turn_task"] and not ctx.session_context["turn_task"].done():
                            ctx.session_context["turn_task"].cancel()
                        
                        ctx.session_context["turn_task"] = TaskRegistry.track(
                            turn_processor.process_turn(transcript_override=override_text),
                            name=f"process_turn_trigger:{session_id[:8] if session_id else 'unknown'}",
                            session_id=session_id,
                        )

                elif msg_type == "abort":
                    logger.info(f"[WS] Abort received. Buffer had {len(audio_buffer)} bytes. Clearing.")
                    audio_buffer = bytearray()
                    accepting_audio = True
                    if ctx.session_context["turn_task"] and not ctx.session_context["turn_task"].done():
                        ctx.session_context["turn_task"].cancel()
                        ctx.session_context["turn_task"] = None
                    try:
                        if isinstance(ctx.stt_stream, DeepgramStreamService) and ctx.stt_stream.is_stream_active:
                            asyncio.create_task(ctx.stt_stream.stop())
                            ctx.ctx.stt_stream = None
                            ctx.ctx.ctx.stt_stream_ready = False
                        if ctx.client_active:
                            await websocket.send_json({"type": "status", "status": "idle"})
                    except Exception:
                        pass
                        
                elif msg_type == "interrupt":
                    new_seq_id = data.get("new_sequence_id")
                    if new_seq_id is None and session_id and redis_pool:
                        try:
                            curr_seq = await redis_pool.hget(f"asta:session:{session_id}", "sequence_id")
                            new_seq_id = int(curr_seq or 0) + 1
                        except Exception as e:
                            logger.error(f"[WS] Redis error during interrupt sequence check: {e}")
                            new_seq_id = 1
                    elif new_seq_id is None:
                        new_seq_id = 1
                        
                    if session_id and redis_pool:
                        try:
                            await redis_pool.hset(f"asta:session:{session_id}", "sequence_id", new_seq_id)
                            await redis_pool.hset(f"asta:session:{session_id}", "is_interrupted", "true")
                        except Exception as e:
                            logger.error(f"[WS] Redis error during interrupt set: {e}")
                        
                    logger.info(f"[WS] Barge-In INTERRUPT. Syncing Seq ID: {new_seq_id}")
                    
                    if ctx.session_context["tts_worker_task"] and not ctx.session_context["tts_worker_task"].done():
                        ctx.session_context["tts_worker_task"].cancel()
                        ctx.session_context["tts_worker_task"] = None
                    if ctx.session_context["turn_task"] and not ctx.session_context["turn_task"].done():
                        ctx.session_context["turn_task"].cancel()
                        ctx.session_context["turn_task"] = None
                    
                    if ctx.stt_connect_task and not ctx.stt_connect_task.done():
                        ctx.stt_connect_task.cancel()
                        ctx.ctx.stt_connect_task = None

                    if isinstance(ctx.stt_stream, DeepgramStreamService) and ctx.stt_stream.is_stream_active:
                        asyncio.create_task(ctx.stt_stream.stop())
                        
                    ctx.ctx.stt_stream = None
                    ctx.ctx.ctx.stt_stream_ready = False
                        
                    # Clear any queue residues if needed
                    audio_buffer = bytearray()
                    accepting_audio = True
                    try:
                        if ctx.client_active:
                            await websocket.send_json({"type": "status", "status": "idle"})
                    except Exception:
                        pass

                elif msg_type == "turn_end":
                    logger.info(f"[WS] turn_end received. Buffer size: {len(audio_buffer)} bytes")
                    accepting_audio = False  # Block orphan chunks from polluting next buffer
                    
                    # Block new turns during TOOL_EXECUTING state
                    if ctx.tsm and getattr(ctx.tsm, 'state', None) == TurnState.TOOL_EXECUTING:
                        if ctx.client_active:
                            await websocket.send_json({"type": "warning", "message": "Still executing tool — I'll handle this right after."})
                        accepting_audio = True
                        continue
                    
                    if ctx.session_context["turn_task"] and not ctx.session_context["turn_task"].done():
                        if ctx.client_active:
                            await websocket.send_json({"type": "warning", "message": "Already processing."})
                        accepting_audio = True
                        continue

                    if not audio_buffer:
                        logger.info("[WS] Empty audio buffer on turn_end, returning to listening")
                        if ctx.client_active:
                            await websocket.send_json({"type": "status", "status": "listening"})
                        audio_buffer = bytearray()  # Clear any stray bytes
                        accepting_audio = True
                        continue

                    from backend.app.core.rate_limiter import ws_rate_limiter
                    
                    if not ws_rate_limiter.check(session_id or getattr(websocket.client, "host", "unknown")):
                        logger.warning(f"[RateLimit] Rate limit exceeded for {session_id}")
                        if ctx.client_active:
                            asyncio.create_task(broadcast_error(websocket, "RateLimit", "Whoa, too fast! Give me a second."))
                        
                        audio_buffer = bytearray()
                        accepting_audio = True
                        continue

                    current_audio = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    accepting_audio = True  # Re-enable for next turn

                    ctx.session_context["turn_task"] = TaskRegistry.track(
                        turn_processor.process_turn(audio_data=current_audio),
                        name=f"process_turn_audio:{session_id[:8] if session_id else 'unknown'}",
                        session_id=session_id,
                    )



                elif msg_type == "text_input":
                    text = data.get("text", "")
                    logger.info(f"[WS] text_input received: {text[:50]}")
                    

                    
                    # Block text input during TOOL_EXECUTING
                    if ctx.tsm and getattr(ctx.tsm, 'state', None) == TurnState.TOOL_EXECUTING:
                        if ctx.client_active:
                            await websocket.send_json({"type": "warning", "message": "Still executing tool — I'll handle this right after."})
                        continue
                    
                    from backend.app.core.rate_limiter import ws_rate_limiter
                    if not ws_rate_limiter.check(session_id or getattr(websocket.client, "host", "unknown")):
                        logger.warning(f"[RateLimit] Rate limit exceeded for {session_id}")
                        if ctx.client_active:
                            asyncio.create_task(broadcast_error(websocket, "RateLimit", "Whoa, too fast! Give me a second."))
                        continue
                    
                    if ctx.session_context["turn_task"] and not ctx.session_context["turn_task"].done():
                        ctx.session_context["turn_task"].cancel()
                        ctx.session_context["turn_task"] = None
                    
                    audio_buffer = bytearray() # Clear any audio
                    ctx.session_context["turn_task"] = TaskRegistry.track(
                        turn_processor.process_turn(transcript_override=text),
                        name=f"process_turn_text:{session_id[:8] if session_id else 'unknown'}",
                        session_id=session_id,
                    )
    except Exception as e:
        logger.error(f"[WS] Critical Connection Error: {e}")
    finally:
        ctx.ctx.client_active = False # Ensure no residual tasks push messages
        _active_connections.discard(websocket)
        if ctx.session_context["turn_task"] and not ctx.session_context["turn_task"].done():
            ctx.session_context["turn_task"].cancel()
        if ctx.session_context["tts_worker_task"] and not ctx.session_context["tts_worker_task"].done():
            ctx.session_context["tts_worker_task"].cancel()
        if ctx.stt_connect_task and not ctx.stt_connect_task.done():
            ctx.stt_connect_task.cancel()
        
        if isinstance(ctx.stt_stream, DeepgramStreamService) and ctx.stt_stream.is_stream_active:
            asyncio.create_task(ctx.stt_stream.stop())
            ctx.ctx.stt_stream = None
            ctx.ctx.ctx.stt_stream_ready = False
            
        if session_id:
            # Cancel all tracked tasks for this session
            TaskRegistry.cancel_all(session_id)
            logger.info("[WS] Socket Closed. Memory migrating to L3 in background.")
            # Session cleanup is handled by SessionManager
            try:
                from backend.app.services.session_manager import SessionManager
                await SessionManager.mark_finalizing_and_enqueue(session_id)
            except Exception as e:
                logger.error(f"[WS] Error finalizing session {session_id}: {e}")
        else:
            logger.info("[WS] Socket lifecycle closed safely.")
