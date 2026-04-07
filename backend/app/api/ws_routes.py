from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.services.stt_service import transcribe_audio
from backend.app.services.llm_service import stream_llm_response
from backend.app.services.tts_service import synthesize_speech_stream
from backend.app.db.session import save_message, get_history
from backend.app.db.memory_handler import memory_handler
from backend.app.core.registry import safe_get, registry
from backend.app.services.l1_cache import l1_manager
from backend.app.core.circuit_breaker import status_registry
from backend.app.speech.deepgram_stream import DeepgramStreamService
from backend.app.services.graph_service import l3_manager
import json, asyncio, logging, re, struct, uuid

logger = logging.getLogger("WS_Conversation")

router = APIRouter()

async def broadcast_error(websocket: WebSocket, error_type: str, message: str):
    """Send error to frontend and log. Used for TTS timeout handling."""
    try:
        await websocket.send_json({"type": "error", "message": message})
        logger.error(f"[TTS] {error_type}: {message}")
    except Exception as e:
        logger.error(f"[broadcast_error] Failed to send: {e}")

async def fetch_memory_context(user_message: str, session_id: str):
    history = None
    rag_context = None
    tool_injection = ""
    try:
        if session_id:
            # IMMEDIATELY get L1 history (never blocks)
            history = l1_manager.get_session(session_id).get_llm_history()
            
            # THE ZERO-LATENCY HANDSHAKE (L1.5 Layer)
            spec_data = await l1_manager.get_session(session_id).get_speculative_data("prefetch_rag")
            if spec_data:
                trigger_query = spec_data.get("trigger_query", "")
                data = spec_data.get("data", "")
                
                # Check semantic overlap to prevent off-topic shifts
                words1 = set(re.findall(r'\w+', user_message.lower()))
                words2 = set(re.findall(r'\w+', trigger_query.lower()))
                
                # Calculate overlap ratio relative to the shorter string
                shorter = min(len(words1), len(words2))
                overlap_ratio = len(words1.intersection(words2)) / shorter if shorter > 0 else 0
                
                if overlap_ratio >= 0.3 or len(words1) < 4:
                    logger.info(f"[L1.5 Handshake] HIT | Overlap: {overlap_ratio:.2f} | Query: '{trigger_query}' -> '{user_message}'")
                    rag_context = data
                else:
                    logger.info(f"[L1.5 Handshake] REJECTED | Overlap too low: {overlap_ratio:.2f} (User shifted topic)")
                    rag_context = None

            # CHECK FOR SPECULATIVE TOOL RESULTS
            # Assuming possible tool is 'WebSearch' for now, or we iterate over known tools.
            # For simplicity, we can fetch all or just WebSearch
            tool_data = await l1_manager.get_session(session_id).get_speculative_data("tool_result_WebSearch")
            if tool_data and tool_data.get("status") == "success":
                tool_txt = tool_data.get("data", "")
                tool_injection = f"\n<tool_output>\n[SUPPLEMENTAL_TOOL_DATA: WebSearch]\n{tool_txt}\n</tool_output>\n"
                logger.info("[L1.5 Tools] Tool Result Context Injected")
                # Clear the result so it doesn't pollute subsequent queries
                l1_manager.get_session(session_id).set_speculative_data("tool_result_WebSearch", None)

        if not rag_context:
            import backend.app.services.memory_orchestrator as mo
            try:
                top_matches = await mo.orchestrator.cross_tier_retrieve(user_message)
                if top_matches:
                    rag_context = top_matches
            except Exception as query_err:
                logger.error(f"[MEMORY] Cross Tier failed: {query_err}")
                rag_context = "I'm having trouble accessing my long-term memory banks right now, but I'm Asta, and I'm here to help while the connection stabilizes."
    except Exception as e:
        logger.warning(f"[MEMORY] Offline Mode Active (Failed to connect: {e})")
        rag_context = "I'm having trouble accessing my long-term memory banks right now, but I'm Asta, and I'm here to help while the connection stabilizes."
        
    final_rag_context = ""
    if rag_context:
        final_rag_context += rag_context
    if tool_injection:
        final_rag_context += tool_injection
        
    return history, final_rag_context if final_rag_context else None

@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    await websocket.accept()
    logger.info("[WS] Client connected")
    session_id = None
    audio_buffer = bytearray()
    
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
                                # KEYWORD FILTER: Only prefetch if transcript contains user property
                                try:
                                    identity = l3_manager.get_user_identity("KARTHIK")
                                    properties = identity.get("properties", []) if identity else []
                                    text_lower = text.lower()
                                    keyword_match = any(prop.lower() in text_lower for prop in properties)
                                    
                                    if keyword_match:
                                        last_prefetch_time = now
                                        import backend.app.services.memory_orchestrator as mo
                                        asyncio.create_task(mo.orchestrator.speculative_prefetch(text, session_id))
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
        
    async def process_turn(audio_data=None, transcript_override=None):
        nonlocal session_id, redis_pool, client_active, stt_stream, stt_stream_ready, stt_connect_task
        
        if not client_active:
            return
        
        current_turn_id = str(uuid.uuid4())
        
        if session_id and redis_pool:
            try:
                await redis_pool.hset(f"asta:session:{session_id}", "current_turn_id", current_turn_id)
            except Exception as e:
                logger.error(f"[WS] Redis error during process_turn hset: {e}")

        try:
            if audio_data:
                logger.info(f"[TURN] Processing {len(audio_data)} bytes of audio")
            
            if client_active:
                await websocket.send_json({"type": "status", "status": "processing", "turn_id": current_turn_id})
            
            if transcript_override is not None:
                transcript = transcript_override
            else:
                if stt_connect_task and not stt_connect_task.done():
                    logger.info("[STT L1.5] Turn ended before connect finished, bypassing to REST API")
                    stt_connect_task.cancel()
                    stt_connect_task = None
                    stt_stream = None
                    stt_stream_ready = False

                if isinstance(stt_stream, DeepgramStreamService) and stt_stream.is_stream_active:
                    stt_result = await stt_stream.finish()
                    transcript = stt_result.get("text", "")
                    stt_stream = None # Reset for next turn
                    stt_stream_ready = False
                else:
                    transcript = await transcribe_audio(audio_data)
                
            if not transcript or not transcript.strip():
                if client_active:
                    await websocket.send_json({"type": "status", "status": "listening", "turn_id": current_turn_id})
                return

            if client_active:
                await websocket.send_json({"type": "transcript", "text": transcript, "turn_id": current_turn_id})

            async def stream_parallel_turn():
                import websockets
                import base64
                from backend.app.config import config as settings
                import struct
                
                if client_active:
                    await websocket.send_json({"type": "status", "status": "thinking", "turn_id": current_turn_id})

                mem_task = asyncio.create_task(fetch_memory_context(transcript, session_id))
                history, rag_context = None, None
                
                if session_id:
                    history = l1_manager.get_session(session_id).get_llm_history()
                    
                try:
                    _, rag_context = await asyncio.wait_for(asyncio.shield(mem_task), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("[MEMORY] Context injection missed 10.0s window. Using history only.")

                if not client_active:
                    return

                dg_ws_url = "wss://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=24000"
                dg_headers = {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}

                token_queue = asyncio.Queue()
                full_response = []

                async def llm_generator():
                    try:
                        # Get current memory mode for health-aware LLM inference
                        memory_mode = status_registry.get_memory_mode()
                        
                        async for text_chunk in stream_llm_response(transcript, session_id, history, rag_context, health_status=memory_mode):
                            if not client_active: break
                            full_response.append(text_chunk)
                            try:
                                await websocket.send_json({"type": "llm_chunk", "text": text_chunk, "turn_id": current_turn_id})
                            except Exception as chunk_err:
                                logger.warning(f"[LLM] Failed sending chunk to client (socket dead?): {chunk_err}")
                                break # Stop generating if client socket is dead
                            await token_queue.put(text_chunk)
                    except Exception as e:
                        logger.error(f"[LLM] Generator failed: {e}")
                        err_str = str(e).lower()
                        if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                            try:
                                if client_active:
                                    await websocket.send_json({"type": "error", "message": "Brain is resting (Rate Limit). Try again in a few minutes."})
                            except Exception as err_err:
                                logger.error(f"[LLM] Failed to send rate limit message: {err_err}")
                    finally:
                        await token_queue.put(None)

                async def deepgram_pusher(dg_ws):
                    try:
                        text_buffer = ""
                        while client_active:
                            llm_text = await token_queue.get()
                            if llm_text is None:
                                if text_buffer.strip():
                                    await dg_ws.send(json.dumps({"type": "Speak", "text": text_buffer}))
                                await dg_ws.send(json.dumps({"type": "Flush"}))
                                await dg_ws.send(json.dumps({"type": "Close"}))
                                break
                            
                            text_buffer += llm_text
                            # Flush on punctuation or space
                            if any(char in text_buffer for char in " .,!?\n") and len(text_buffer) >= 2:
                                await dg_ws.send(json.dumps({"type": "Speak", "text": text_buffer}))
                                text_buffer = ""
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.warning(f"[DG] TTS websocket sent close: {e}")
                        if client_active:
                            await broadcast_error(websocket, "TTS_TIMEOUT", "TTS service connection lost. Please try again.")
                    except Exception as e:
                        logger.error(f"[DG] Pusher failed: {e}")
                        if client_active:
                            await broadcast_error(websocket, "TTS_ERROR", f"TTS service error: {e}")

                async def client_pusher(dg_ws):
                    seq_id = 0
                    if session_id and redis_pool:
                        try:
                            seq_str = await redis_pool.hget(f"asta:session:{session_id}", "sequence_id")
                            seq_id = int(seq_str) if seq_str else 0
                        except Exception:
                            pass
                            
                    try:
                        first_chunk = True
                        while client_active:
                            msg = await dg_ws.recv()
                            if isinstance(msg, bytes):
                                if first_chunk:
                                    first_chunk = False
                                    try:
                                        await websocket.send_json({"type": "status", "status": "speaking", "turn_id": current_turn_id})
                                    except Exception: pass
                                    
                                seq_header = struct.pack(">I", seq_id)
                                combined = seq_header + msg
                                encoded = base64.b64encode(combined).decode("utf-8")
                                
                                try:
                                    await websocket.send_json({
                                        "type": "audio",
                                        "data": encoded
                                    })
                                except Exception: pass
                            elif isinstance(msg, str):
                                data = json.loads(msg)
                                if data.get("type") == "Flushed" or data.get("type") == "Warning":
                                    pass
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.warning(f"[CLI] TTS websocket closed early: {e}")
                    except Exception as e:
                        logger.error(f"[CLI] Pusher failed: {e}")

                # 1. ALWAYS start the LLM so text streams to the user regardless of audio service
                task_a = asyncio.create_task(llm_generator())
                
                try:
                    import websockets
                    try:
                        dg_ws_context = websockets.connect(dg_ws_url, additional_headers=dg_headers)
                    except TypeError:
                        dg_ws_context = websockets.connect(dg_ws_url, extra_headers=list(dg_headers.items()))
                        
                    async with dg_ws_context as dg_ws:
                        task_b = asyncio.create_task(deepgram_pusher(dg_ws))
                        task_c = asyncio.create_task(client_pusher(dg_ws))
                        
                        session_context["tts_worker_task"] = task_c
                        
                        await asyncio.gather(task_a, task_b, task_c)
                except Exception as ws_err:
                    import traceback
                    logger.error(f"[WS] Error connecting to Deepgram TTS: {ws_err}\n{traceback.format_exc()}")
                    # Since Deepgram failed, block and await the LLM task so text generation continues back to user
                    await task_a

                final_text = "".join(full_response)
                logger.info(f"[TURN] LLM & TTS complete: '{final_text[:80]}...'")
                
                try:
                    if client_active:
                        await websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                except Exception:
                    pass
                
                if session_id:
                    await l1_manager.get_session(session_id).append_turn(transcript, final_text)
                    try:
                        from backend.app.services.session_manager import SessionManager
                        await SessionManager.add_message(session_id, "user", transcript)
                        await SessionManager.add_message(session_id, "assistant", final_text)
                    except Exception as e:
                        logger.error(f"[WS] Error saving messages to SessionManager: {e}")

            # Execute the parallel turn
            await stream_parallel_turn()
        except asyncio.CancelledError:
            logger.info("[TURN] Cancelled by user (abort)")
        except Exception as e:
            logger.error(f"[TURN] Error: {type(e).__name__}: {e}")
            try:
                if client_active:
                    await websocket.send_json({"type": "error", "message": f"Processing fail: {e}"})
            except:
                pass

    accepting_audio = True

    try:
        while client_active:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                logger.info("[WS] Client disconnected natively")
                break
            except RuntimeError as e:
                # Catch RuntimeError when socket drops mid receive
                if "WebSocket is not connected" in str(e):
                    break
                raise e

            if "bytes" in message:
                if accepting_audio:
                    audio_buffer.extend(message["bytes"])
                    # Send bytes to streaming engine if active
                    if not stt_stream:
                        stt_stream = True # Lock to prevent multiple creations immediately
                        stt_connect_task = asyncio.create_task(start_stt_stream())
                    elif stt_stream_ready and isinstance(stt_stream, DeepgramStreamService):
                        asyncio.create_task(stt_stream.send_audio(message["bytes"]))

            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    if client_active:
                        await websocket.send_json({"type": "error", "message": "Invalid JSON control message"})
                    continue

                msg_type = data.get("type")
                logger.info(f"[WS] Control message: {msg_type}")

                if msg_type == "session_start":
                    session_id = data.get("session_id")
                    if session_id and redis_pool:
                        try:
                            exists = await redis_pool.exists(f"asta:session:{session_id}")
                            if not exists:
                                await redis_pool.hset(f"asta:session:{session_id}", mapping={"sequence_id": 0, "is_interrupted": "false", "current_turn_id": ""})
                                await redis_pool.expire(f"asta:session:{session_id}", 1800)
                        except Exception as e:
                            logger.error(f"[WS] Redis error during session_start: {e}")
                    if client_active:
                        await websocket.send_json({"type": "ready"})

                elif msg_type == "abort":
                    logger.info(f"[WS] Abort received. Buffer had {len(audio_buffer)} bytes. Clearing.")
                    audio_buffer = bytearray()
                    accepting_audio = True
                    if session_context["turn_task"] and not session_context["turn_task"].done():
                        session_context["turn_task"].cancel()
                        session_context["turn_task"] = None
                    try:
                        if isinstance(stt_stream, DeepgramStreamService) and stt_stream.is_stream_active:
                            asyncio.create_task(stt_stream.stop())
                            stt_stream = None
                            stt_stream_ready = False
                        if client_active:
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
                    
                    if session_context["tts_worker_task"] and not session_context["tts_worker_task"].done():
                        session_context["tts_worker_task"].cancel()
                        session_context["tts_worker_task"] = None
                    if session_context["turn_task"] and not session_context["turn_task"].done():
                        session_context["turn_task"].cancel()
                        session_context["turn_task"] = None
                    
                    if stt_connect_task and not stt_connect_task.done():
                        stt_connect_task.cancel()
                        stt_connect_task = None

                    if isinstance(stt_stream, DeepgramStreamService) and stt_stream.is_stream_active:
                        asyncio.create_task(stt_stream.stop())
                        
                    stt_stream = None
                    stt_stream_ready = False
                        
                    # Clear any queue residues if needed
                    audio_buffer = bytearray()
                    accepting_audio = True
                    try:
                        if client_active:
                            await websocket.send_json({"type": "status", "status": "idle"})
                    except Exception:
                        pass

                elif msg_type == "turn_end":
                    logger.info(f"[WS] turn_end received. Buffer size: {len(audio_buffer)} bytes")
                    accepting_audio = False  # Block orphan chunks from polluting next buffer
                    
                    if session_context["turn_task"] and not session_context["turn_task"].done():
                        if client_active:
                            await websocket.send_json({"type": "warning", "message": "Already processing."})
                        accepting_audio = True
                        continue

                    if not audio_buffer:
                        logger.info("[WS] Empty audio buffer on turn_end, returning to listening")
                        if client_active:
                            await websocket.send_json({"type": "status", "status": "listening"})
                        audio_buffer = bytearray()  # Clear any stray bytes
                        accepting_audio = True
                        continue

                    current_audio = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    accepting_audio = True  # Re-enable for next turn

                    session_context["turn_task"] = asyncio.create_task(process_turn(audio_data=current_audio))

                elif msg_type == "text_input":
                    text = data.get("text", "")
                    logger.info(f"[WS] text_input received: {text[:50]}")
                    
                    if session_context["turn_task"] and not session_context["turn_task"].done():
                        session_context["turn_task"].cancel()
                        session_context["turn_task"] = None
                    
                    audio_buffer = bytearray() # Clear any audio
                    session_context["turn_task"] = asyncio.create_task(process_turn(transcript_override=text))
    except Exception as e:
        logger.error(f"[WS] Critical Connection Error: {e}")
    finally:
        client_active = False # Ensure no residual tasks push messages
        if session_context["turn_task"] and not session_context["turn_task"].done():
            session_context["turn_task"].cancel()
        if session_context["tts_worker_task"] and not session_context["tts_worker_task"].done():
            session_context["tts_worker_task"].cancel()
        if stt_connect_task and not stt_connect_task.done():
            stt_connect_task.cancel()
        
        if isinstance(stt_stream, DeepgramStreamService) and stt_stream.is_stream_active:
            asyncio.create_task(stt_stream.stop())
            stt_stream = None
            stt_stream_ready = False
            
        if session_id:
            logger.info("[WS] Socket Closed. Memory migrating to L3 in background.")
            await l1_manager.clear_session(session_id)
            try:
                from backend.app.services.session_manager import SessionManager
                await SessionManager.mark_finalizing_and_enqueue(session_id)
            except Exception as e:
                logger.error(f"[WS] Error finalizing session {session_id}: {e}")
        else:
            logger.info("[WS] Socket lifecycle closed safely.")
