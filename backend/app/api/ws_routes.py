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
from memory.graph_service import graph_service as l3_manager
from backend.app.services.llm_hardening import sanitize_input
from backend.app.services.security import verify_websocket_api_key
from backend.app.models.action_model import ActionRequest
from backend.app.core.turn_state import TurnStateMachine, TurnState
from backend.app.core.task_registry import TaskRegistry
import json, asyncio, logging, re, struct, uuid

logger = logging.getLogger("WS_Conversation")

router = APIRouter()

# Bearer token shared with /api/chat (ASTA_API_BEARER_TOKEN). Browsers can't
# set custom headers on a WebSocket handshake, so we also accept ?token=...
_WS_BEARER_TOKEN = os.getenv("ASTA_API_BEARER_TOKEN", "").strip()


def _verify_ws_token(websocket: WebSocket) -> bool:
    """Check the bearer token on a WS handshake (query param or Authorization header)."""
    if not _WS_BEARER_TOKEN:
        logger.error("[WS] ASTA_API_BEARER_TOKEN not configured — rejecting connection")
        return False

    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ", 1)[1].strip()

    return bool(token) and hmac.compare_digest(token, _WS_BEARER_TOKEN)


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

async def broadcast_error(websocket: WebSocket, error_type: str, message: str):
    """Send error to frontend and log. Used for TTS timeout handling."""
    try:
        await websocket.send_json({"type": "error", "message": message})
        logger.error(f"[TTS] {error_type}: {message}")
    except Exception as e:
        logger.error(f"[broadcast_error] Failed to send: {e}")

async def fetch_memory_context(user_message: str, session_id: str, skip_rag: bool = False):
    """
    Fetch conversation history and RAG context.
    
    Args:
        user_message: The user's message
        session_id: Current session ID
        skip_rag: If True, skip RAG retrieval (for casual/tool intents)
    """
    history = None
    rag_context = None
    tool_injection = ""
    
    try:
        if session_id:
            # IMMEDIATELY get L1 history (never blocks)
            history = l1_manager.get_session(session_id).get_llm_history()
            
            # CHECK FOR SPECULATIVE TOOL RESULTS
            # Look for all supported tools rather than just WebSearch
            supported_tools = ["WebSearch", "SkillsRetriever", "openclaw_exec", "search", "weather", "news", "notion", "calendar", "image"]
            for tool_name in supported_tools:
                tool_data = await l1_manager.get_session(session_id).get_speculative_data(f"tool_result_{tool_name}")
                if tool_data and tool_data.get("status") == "success":
                    tool_txt = tool_data.get("data", "")
                    tool_injection += f"\n<tool_output>\n[SUPPLEMENTAL_TOOL_DATA: {tool_name}]\n{tool_txt}\n</tool_output>\n"
                    logger.info(f"[L1.5 Tools] {tool_name} Result Context Injected")
                    # Clear the result so it doesn't pollute subsequent queries
                    l1_manager.get_session(session_id).set_speculative_data(f"tool_result_{tool_name}", None)
            
            # Skip RAG if intent detector says so (casual/tool intents)
            if skip_rag:
                logger.info(f"[INTENT] Skipping RAG retrieval for: '{user_message[:50]}'")
            else:
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

                if not rag_context:
                    import backend.app.services.memory_orchestrator as mo
                    try:
                        top_matches = await mo.orchestrator.cross_tier_retrieve(user_message)
                        if top_matches:
                            rag_context = top_matches
                    except Exception as query_err:
                        logger.error(f"[MEMORY] Cross Tier failed: {query_err}")
                        rag_context = None
    except Exception as e:
        logger.warning(f"[MEMORY] Offline Mode Active (Failed to connect: {e})")
        rag_context = None
        
    final_rag_context = ""
    if rag_context:
        final_rag_context += rag_context
    if tool_injection:
        final_rag_context += tool_injection
        
    return history, final_rag_context if final_rag_context else None

@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    if not _verify_ws_token(websocket):
        await websocket.close(code=4001)
        logger.warning("[WS] Unauthorized connection rejected")
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
                                # KEYWORD FILTER: Only prefetch if transcript contains user property
                                try:
                                    identity = await l3_manager.get_user_identity("KARTHIK")
                                    properties = identity.get("properties", []) if identity else []
                                    text_lower = text.lower()
                                    keyword_match = any(prop.lower() in text_lower for prop in properties)
                                    
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
        
    async def process_turn(audio_data=None, transcript_override=None):
        nonlocal session_id, redis_pool, client_active, stt_stream, stt_stream_ready, stt_connect_task, tsm
        
        if not client_active:
            return
        
        current_turn_id = str(uuid.uuid4())
        
        if not tsm or tsm.turn_id != current_turn_id:
            from backend.app.core.turn_state import TurnStateMachine, TurnState
            tsm = TurnStateMachine(session_id or "unknown", current_turn_id)
            await tsm.transition(TurnState.LISTENING)
            
        if session_id and redis_pool:
            try:
                await redis_pool.hset(f"asta:session:{session_id}", "current_turn_id", current_turn_id)
            except Exception as e:
                logger.error(f"[WS] Redis error during process_turn hset: {e}")

        try:
            if audio_data:
                logger.info(f"[TURN] Processing {len(audio_data)} bytes of audio")
            
            await tsm.transition(TurnState.PROCESSING)
            
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
                if tsm.state != TurnState.IDLE:
                    await tsm.transition(TurnState.IDLE)
                if client_active:
                    await websocket.send_json({"type": "status", "status": "listening", "turn_id": current_turn_id})
                return

            # SECURITY: Sanitize transcript against prompt injection attacks
            transcript = sanitize_input(transcript)

            if client_active:
                await websocket.send_json({"type": "transcript", "text": transcript, "turn_id": current_turn_id})

            async def stream_parallel_turn():
                import websockets
                import base64
                from backend.app.config import config as settings
                from backend.app.services.intent_detector import intent_detector
                import struct
                
                await tsm.transition(TurnState.THINKING)
                
                if client_active:
                    await websocket.send_json({"type": "status", "status": "thinking", "turn_id": current_turn_id})

                # INTENT DETECTION - Route based on user intent
                intent = intent_detector.detect(transcript)
                logger.info(f"[INTENT] Detected: {intent['type']} (confidence={intent['confidence']:.2f}) - {intent['reasoning']}")
                
                # Fetch memory context based on intent
                skip_rag = intent_detector.should_skip_rag(intent)
                mem_task = asyncio.create_task(fetch_memory_context(transcript, session_id, skip_rag=skip_rag))
                history, rag_context = None, None
                
                if session_id:
                    history = l1_manager.get_session(session_id).get_llm_history()
                    
                try:
                    _, rag_context = await asyncio.wait_for(asyncio.shield(mem_task), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("[MEMORY] Context injection missed 10.0s window. Using history only.")

                if not client_active:
                    return

                # Get forced tool from intent detector first
                forced_tool = intent_detector.get_forced_tool(intent)
                
                # Check if we should route to supervisor for workflow execution
                # Notion, routine, research, and content intents should use workflows
                workflow_keywords = ["notion", "task", "routine", "research", "linkedin", "content", "morning", "night", "plan"]
                should_use_workflow = (
                    forced_tool == "notion" or
                    intent['type'] in ['routine', 'research', 'content'] or
                    any(kw in transcript.lower() for kw in workflow_keywords)
                )
                
                if should_use_workflow:
                    logger.info(f"[WORKFLOW] Routing to supervisor for workflow execution")
                    
                    try:
                        from backend.app.core.supervisor_graph import run_supervisor_graph

                        # Run supervisor graph (it classifies + routes internally)
                        await tsm.transition(TurnState.TOOL_PENDING)
                        await tsm.transition(TurnState.TOOL_EXECUTING)

                        try:
                            await websocket.send_json({"type": "llm_chunk", "text": "Let me check that for you, boss...\n", "turn_id": current_turn_id})
                        except Exception:
                            pass

                        # Execute supervisor graph
                        result = await asyncio.wait_for(
                            run_supervisor_graph(
                                session_id=session_id,
                                user_input=transcript,
                                messages=(history or []),
                            ),
                            timeout=60.0
                        )

                        await tsm.resolve_tool(result)

                        # Get response from supervisor (graph returns "response")
                        response_text = result.get("response") or result.get("asta_response", "Task completed.")
                        logger.info(f"[WORKFLOW] Supervisor completed: {result.get('workflow_type', 'unknown')} workflow")
                        
                        # Stream response to client
                        try:
                            # Send response in chunks for better UX
                            chunk_size = 50
                            for i in range(0, len(response_text), chunk_size):
                                chunk = response_text[i:i+chunk_size]
                                await websocket.send_json({"type": "llm_chunk", "text": chunk, "turn_id": current_turn_id})
                                await asyncio.sleep(0.05)  # Small delay for streaming effect
                            
                            await websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                        except Exception:
                            pass
                        
                        # Save to session
                        if session_id:
                            await l1_manager.get_session(session_id).append_turn(transcript, response_text)
                            try:
                                from backend.app.services.session_manager import SessionManager
                                await SessionManager.add_message(session_id, "user", transcript)
                                await SessionManager.add_message(session_id, "assistant", response_text)
                            except Exception as e:
                                logger.error(f"[WS] Error saving workflow messages: {e}")
                        
                        await tsm.transition(TurnState.IDLE)
                        return  # Exit early, workflow handled everything
                        
                    except asyncio.TimeoutError:
                        logger.error("[WORKFLOW] Supervisor execution timed out")
                        await tsm.fail_tool("Workflow execution timed out")
                        error_msg = "Sorry boss, that took too long. Let me try a different approach."
                        try:
                            await websocket.send_json({"type": "llm_chunk", "text": error_msg, "turn_id": current_turn_id})
                        except Exception:
                            pass
                        # Fall through to regular LLM
                    except Exception as workflow_err:
                        logger.error(f"[WORKFLOW] Supervisor execution failed: {workflow_err}", exc_info=True)
                        await tsm.fail_tool(str(workflow_err))
                        # Fall through to regular LLM to explain the error
                
                # Check if we should force a tool call (for non-workflow tools)
                if forced_tool and intent['type'] == 'tool' and not should_use_workflow:
                    logger.info(f"[INTENT] Forcing tool call: {forced_tool}")
                    
                    # Build tool payload based on detected tool
                    tool_payload = None
                    
                    if forced_tool == "weather":
                        # Extract city from message or use default
                        city = "San Francisco"  # Default
                        # Simple city extraction
                        words = transcript.split()
                        for i, word in enumerate(words):
                            if word.lower() in ["in", "at", "for"] and i + 1 < len(words):
                                city = " ".join(words[i+1:])
                                break
                        
                        tool_payload = {
                            "action": "api_tool",
                            "tool": "weather",
                            "operation": "get_current",
                            "city": city,
                            "intent": f"Get weather for {city}",
                            "memory_tag": "weather_query"
                        }
                    
                    elif forced_tool == "search":
                        # Extract search query
                        query = transcript
                        # Remove common search prefixes
                        for prefix in ["search for", "search", "google", "find", "look up", "what is", "who is", "tell me about"]:
                            if query.lower().startswith(prefix):
                                query = query[len(prefix):].strip()
                                break
                        
                        tool_payload = {
                            "action": "api_tool",
                            "tool": "search",
                            "operation": "search",
                            "query": query,
                            "num_results": 5,
                            "intent": f"Search for: {query}",
                            "memory_tag": "search_query"
                        }
                    
                    elif forced_tool == "news":
                        # Extract topic or use general
                        topic = "general"
                        words = transcript.lower().split()
                        if "about" in words:
                            idx = words.index("about")
                            if idx + 1 < len(words):
                                topic = " ".join(words[idx+1:])
                        
                        tool_payload = {
                            "action": "api_tool",
                            "tool": "news",
                            "operation": "get_topic" if topic != "general" else "get_digest",
                            "topic": topic,
                            "topics": [topic] if topic != "general" else ["technology", "business"],
                            "intent": f"Get news about {topic}",
                            "memory_tag": "news_query"
                        }
                    
                    elif forced_tool == "calendar":
                        tool_payload = {
                            "action": "api_tool",
                            "tool": "calendar",
                            "operation": "get_today",
                            "intent": "Check calendar",
                            "memory_tag": "calendar_query"
                        }

                    elif forced_tool == "study_planner":
                        from backend.app.workflows import study_planner

                        await tsm.transition(TurnState.TOOL_PENDING)
                        await tsm.transition(TurnState.TOOL_EXECUTING)

                        try:
                            await websocket.send_json({"type": "llm_chunk", "text": "[Study Planner]\n", "turn_id": current_turn_id})
                        except Exception:
                            pass

                        try:
                            if study_planner.has_active_intake(session_id):
                                result = await study_planner.advance_intake(session_id, transcript)
                            elif any(kw in transcript.lower() for kw in ["today", "what am i", "what should i", "my plan"]):
                                result = await study_planner.get_today_plan(session_id)
                            else:
                                result = await study_planner.run_intake(session_id, mode="voice")

                            if "prompt" in result:
                                result_text = result["prompt"]
                            elif "summary" in result:
                                result_text = result["summary"]
                            else:
                                result_text = str(result)

                            try:
                                await websocket.send_json({"type": "llm_chunk", "text": result_text, "turn_id": current_turn_id})
                                await websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                            except Exception:
                                pass

                            await tsm.resolve_tool(None)
                            logger.info(f"[INTENT] Study planner flow completed: {result.get('stage', 'unknown')}")
                        except Exception as sp_err:
                            logger.error(f"[INTENT] Study planner error: {sp_err}", exc_info=True)
                            await tsm.fail_tool(str(sp_err))
                            try:
                                await websocket.send_json({"type": "llm_chunk", "text": f"Study planner error: {sp_err}", "turn_id": current_turn_id})
                            except Exception:
                                pass
                        return

                    # If we have a tool payload, execute it directly
                    if tool_payload:
                        from backend.app.services.action_executor import action_executor
                        
                        await tsm.transition(TurnState.TOOL_PENDING)
                        await tsm.transition(TurnState.TOOL_EXECUTING)
                        
                        try:
                            await websocket.send_json({"type": "llm_chunk", "text": f"[Checking {forced_tool}...]\n", "turn_id": current_turn_id})
                        except Exception:
                            pass
                        
                        try:
                            req = ActionRequest(
                                session_id=session_id,
                                tool_name=forced_tool,
                                parameters=tool_payload,
                                intent=tool_payload.get("intent", ""),
                                memory_tag=tool_payload.get("memory_tag", ""),
                            )
                            
                            await tsm.dispatch_tool(forced_tool, tool_payload)
                            
                            tool_result = await asyncio.wait_for(
                                action_executor.execute_action(req),
                                timeout=65.0
                            )
                            await tsm.resolve_tool(tool_result)
                            logger.info(f"[INTENT] Forced tool completed: {tool_result.tool_name} -> {tool_result.status}")
                            
                            # Send tool result as response
                            result_text = str(tool_result.result)[:1000]
                            
                            try:
                                await websocket.send_json({"type": "llm_chunk", "text": result_text, "turn_id": current_turn_id})
                                await websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                            except Exception:
                                pass
                            
                            # Save to session
                            if session_id:
                                await tsm.transition(TurnState.IDLE)
                                await l1_manager.get_session(session_id).append_turn(transcript, result_text)
                                try:
                                    from backend.app.services.session_manager import SessionManager
                                    await SessionManager.add_message(session_id, "user", transcript)
                                    await SessionManager.add_message(session_id, "assistant", result_text)
                                except Exception as e:
                                    logger.error(f"[WS] Error saving forced tool messages: {e}")
                                
                                await tsm.transition(TurnState.IDLE)
                            
                            return  # Exit early, tool handled everything
                            
                        except Exception as tool_err:
                            logger.error(f"[INTENT] Forced tool execution failed: {tool_err}")
                            await tsm.fail_tool(str(tool_err))
                            # Fall through to LLM to explain the error

                dg_ws_url = "wss://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=24000"
                dg_headers = {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}

                token_queue = asyncio.Queue()
                full_response = []

                async def llm_generator():
                    try:
                        # Get current memory mode for health-aware LLM inference
                        memory_mode = status_registry.get_memory_mode()
                        
                        # Fetch memory context from session object
                        session_memory_context = ""
                        if session_id:
                            try:
                                from backend.app.services.session_manager import SessionManager
                                _sess = await SessionManager.get_session(session_id)
                                if _sess:
                                    session_memory_context = getattr(_sess, "memory_context", "") or ""
                            except Exception:
                                pass
                        
                        is_json_tool_call = False
                        json_buffer = ""
                        has_started_tts = False
                        
                        async for text_chunk in stream_llm_response(transcript, session_id, history, rag_context, health_status=memory_mode, memory_context=session_memory_context):
                            if not client_active: break
                            full_response.append(text_chunk)
                            json_buffer += text_chunk
                            
                            # Use a sliding window approach for deterministic JSON extraction
                            # If we haven't decided it's NOT a tool yet, and we haven't started TTS:
                            if not has_started_tts and not is_json_tool_call:
                                if "{" in json_buffer:
                                    is_json_tool_call = True
                                elif len(json_buffer.strip()) > 30 and "{" not in json_buffer:
                                    # It's normal text, push everything buffered so far to TTS
                                    has_started_tts = True
                                    for prev_chunk in full_response:
                                        await token_queue.put(prev_chunk)
                            
                            if is_json_tool_call:
                                # We are buffering JSON. Do not push to token_queue.
                                try:
                                    await websocket.send_json({"type": "llm_chunk", "text": text_chunk, "turn_id": current_turn_id})
                                except Exception:
                                    pass
                            else:
                                try:
                                    await websocket.send_json({"type": "llm_chunk", "text": text_chunk, "turn_id": current_turn_id})
                                except Exception as chunk_err:
                                    logger.warning(f"[LLM] Failed sending chunk to client: {chunk_err}")
                                    break
                                
                                if has_started_tts:
                                    await token_queue.put(text_chunk)
                                
                        if is_json_tool_call:
                            # Extract JSON block even if mixed with text
                            import json
                            import re
                            
                            try:
                                # Find everything between the first { and the last }
                                match = re.search(r'\{.*\}', json_buffer, re.DOTALL)
                                if match:
                                    json_str = match.group(0)
                                    tool_payload = json.loads(json_str)

                                action_type = tool_payload.get("action")
                                if action_type in ("openclaw_exec", "browser_search", "api_tool", "workflow"):
                                    from backend.app.services.action_executor import action_executor

                                    await tsm.transition(TurnState.TOOL_PENDING)
                                    await tsm.transition(TurnState.TOOL_EXECUTING)

                                    await websocket.send_json({"type": "llm_chunk", "text": "\n[Executing Tool...]", "turn_id": current_turn_id})
                                    await token_queue.put("Executing autonomous protocol. Keep the comms open.")

                                    resolved_tool = tool_payload.get("tool") or tool_payload.get("action")
                                    await tsm.dispatch_tool(resolved_tool, tool_payload)

                                    try:
                                        req = ActionRequest(
                                            session_id=session_id,
                                            tool_name=resolved_tool,
                                            parameters=tool_payload,
                                            intent=tool_payload.get("intent", ""),
                                            memory_tag=tool_payload.get("memory_tag", ""),
                                        )
                                    except Exception as validation_err:
                                        logger.error(f"[WS] Tool payload validation failed: {validation_err}")
                                        await token_queue.put(f"Security block. Payload rejected: {validation_err}")
                                        await tsm.fail_tool(str(validation_err))
                                        raise
                                    
                                    # BLOCKING AWAIT — do NOT fire-and-forget.
                                    # Turn finalization waits for tool result.
                                    try:
                                        tool_result = await asyncio.wait_for(
                                            action_executor.execute_action(req),
                                            timeout=65.0  # Slightly above executor's internal 60s timeout
                                        )
                                        await tsm.resolve_tool(tool_result)
                                        logger.info(f"[WS] Tool completed: {tool_result.tool_name} -> {tool_result.status}")
                                        
                                        # Inject tool result into TTS so user hears the outcome
                                        result_summary = tool_result.result[:500]
                                        await token_queue.put(f" Tool completed. {result_summary}")
                                        
                                    except asyncio.TimeoutError:
                                        await tsm.fail_tool("Tool execution timed out.")
                                        await token_queue.put("Tool execution timed out. Report this to Karthik.")
                                        logger.error(f"[WS] Tool execution timed out for {tool_payload.get('tool')}")
                                    except Exception as exec_err:
                                        await tsm.fail_tool(str(exec_err))
                                        await token_queue.put(f"Tool execution failed: {exec_err}")
                                        logger.error(f"[WS] Tool execution error: {exec_err}")
                                    
                            except Exception as parse_err:
                                logger.error(f"[WS] Failed to parse/dispatch tool invocation: {parse_err}")
                                
                    except Exception as e:
                        logger.error(f"[LLM] Generator failed: {e}", exc_info=True)
                        err_str = str(e).lower()
                        error_message = "I'm having trouble connecting to my neural network right now."
                        if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                            error_message = "Brain is resting (Rate Limit). Try again in a few minutes."
                        elif "api_key" in err_str or "authentication" in err_str or "credentials" in err_str:
                            error_message = "My API key is missing or invalid."
                            
                        if client_active:
                            try:
                                await websocket.send_json({"type": "error", "message": error_message})
                                await token_queue.put(error_message)
                            except Exception as err_err:
                                logger.error(f"[LLM] Failed to send error message: {err_err}")
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
                                        if tsm.state not in {TurnState.SPEAKING, TurnState.IDLE}:
                                            await tsm.transition(TurnState.SPEAKING)
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
                    # Transition to IDLE after completing response
                    await tsm.transition(TurnState.IDLE)
                    # Commit user message
                    await l1_manager.get_session(session_id).append_turn(transcript, final_text)
                    try:
                        from backend.app.services.session_manager import SessionManager
                        await SessionManager.add_message(session_id, "user", transcript)
                        await SessionManager.add_message(session_id, "assistant", final_text)
                        
                        # MEMORY COMMIT: If a tool executed, commit the result as a first-class message
                        # This ensures tool output persists through L1 → L2 → L3 propagation
                        if tsm.has_tool_result and getattr(tsm.tool_result, 'status', None) == "success":
                            tool_result_msg = tsm.format_tool_result_tag()
                            await SessionManager.add_message(session_id, "assistant", tool_result_msg)
                            # Also commit to L1 so subsequent turns in this session can reference it
                            l1_session = l1_manager.get_session(session_id)
                            if l1_session:
                                # Add the specific tool logic
                                l1_session.set_speculative_data(f"tool_result_{tsm.tool_name}", {
                                    "tool": tsm.tool_name,
                                    "status": getattr(tsm.tool_result, 'status', "success"),
                                    "data": str(tsm.tool_result.result) if hasattr(tsm.tool_result, 'result') else str(tsm.tool_result),
                                    "intent": getattr(tsm.tool_result, 'intent', ""),
                                    "memory_tag": getattr(tsm.tool_result, 'memory_tag', ""),
                                })
                            logger.info(f"[MEMORY_COMMIT] Tool result committed to session: {tsm.tool_name}")
                    except Exception as e:
                        logger.error(f"[WS] Error saving messages to SessionManager: {e}")
                    
                    # Check for pending graph confirmations
                    try:
                        pending = await l3_manager.get_pending_confirmations(session_id)
                        if pending and client_active:
                            # Send graph update prompt to user
                            for confirmation in pending[:1]:  # Only ask about first pending item
                                node_name = confirmation.get("node_name", "")
                                options = confirmation.get("options", [])
                                
                                prompt_text = f"\n\n[GRAPH_UPDATE_NEEDED] I noticed something new: \"{node_name}\"\nWhere should I add this?\n"
                                for idx, option in enumerate(options):
                                    prompt_text += f"{chr(65+idx)}) {option}\n"
                                
                                await websocket.send_json({
                                    "type": "graph_confirmation",
                                    "confirmation_id": str(confirmation.get("_id")),
                                    "node_name": node_name,
                                    "options": options,
                                    "prompt": prompt_text
                                })
                                logger.info(f"[GRAPH] Sent confirmation request for: {node_name}")
                    except Exception as graph_err:
                        logger.error(f"[GRAPH] Failed to check pending confirmations: {graph_err}")
                    
                    finally:
                        # Transition to IDLE for next turn
                        await tsm.transition(TurnState.IDLE)

            # Execute the parallel turn
            await stream_parallel_turn()
        except asyncio.CancelledError:
            logger.info("[TURN] Cancelled by user (abort)")
        except Exception as e:
            logger.error(f"[TURN] Error: {type(e).__name__}: {e}")
            try:
                if client_active:
                    await websocket.send_json({"type": "error", "message": f"Processing fail: {e}"})
            except Exception:
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
                    
                    if client_active:
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
                        if client_active:
                            await websocket.send_json({
                                "type": "wake_word_mode",
                                "enabled": True,
                                "message": "Say the wake word to activate"
                            })
                    else:
                        if client_active:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Wake word detection not available"
                            })
                
                elif msg_type == "disable_wake_word":
                    # Disable wake word detection mode
                    wake_word_mode = False
                    logger.info("[WakeWord] Wake word mode disabled")
                    if client_active:
                        await websocket.send_json({
                            "type": "wake_word_mode",
                            "enabled": False
                        })

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
                    
                    # Block new turns during TOOL_EXECUTING state
                    if tsm and getattr(tsm, 'state', None) == TurnState.TOOL_EXECUTING:
                        if client_active:
                            await websocket.send_json({"type": "warning", "message": "Still executing tool — I'll handle this right after."})
                        accepting_audio = True
                        continue
                    
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

                    from backend.app.core.rate_limiter import ws_rate_limiter
                    
                    if not ws_rate_limiter.check(session_id or getattr(websocket.client, "host", "unknown")):
                        logger.warning(f"[RateLimit] Rate limit exceeded for {session_id}")
                        if client_active:
                            asyncio.create_task(broadcast_error(websocket, "RateLimit", "Whoa, too fast! Give me a second."))
                        
                        audio_buffer = bytearray()
                        accepting_audio = True
                        continue

                    current_audio = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    accepting_audio = True  # Re-enable for next turn

                    session_context["turn_task"] = TaskRegistry.track(
                        process_turn(audio_data=current_audio),
                        name=f"process_turn_audio:{session_id[:8] if session_id else 'unknown'}",
                        session_id=session_id,
                    )

                elif msg_type == "graph_confirmation_response":
                    # Handle user's response to graph confirmation
                    confirmation_id = data.get("confirmation_id")
                    chosen_option = data.get("chosen_option")
                    
                    if not confirmation_id or not chosen_option:
                        logger.warning("[GRAPH] Invalid confirmation response")
                        continue
                    
                    try:
                        success = await l3_manager.resolve_confirmation(
                            confirmation_id=confirmation_id,
                            chosen_option=chosen_option,
                            session_id=session_id
                        )
                        
                        if success and client_active:
                            if chosen_option == "Ignore":
                                await websocket.send_json({
                                    "type": "graph_confirmation_result",
                                    "message": "Got it, I won't add that."
                                })
                            else:
                                await websocket.send_json({
                                    "type": "graph_confirmation_result",
                                    "message": f"Added under {chosen_option}"
                                })
                        logger.info(f"[GRAPH] Confirmation resolved: {chosen_option}")
                    except Exception as e:
                        logger.error(f"[GRAPH] Failed to resolve confirmation: {e}")
                        if client_active:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Failed to update graph"
                            })

                elif msg_type == "text_input":
                    text = data.get("text", "")
                    logger.info(f"[WS] text_input received: {text[:50]}")
                    
                    # Check if this is a graph confirmation response (A/B/C/D)
                    text_upper = text.strip().upper()
                    if text_upper in ["A", "B", "C", "D"] and session_id:
                        try:
                            # Get pending confirmations
                            pending = await l3_manager.get_pending_confirmations(session_id)
                            if pending:
                                confirmation = pending[0]
                                options = confirmation.get("options", [])
                                option_map = {"A": 0, "B": 1, "C": 2, "D": 3}
                                option_idx = option_map.get(text_upper)
                                
                                if option_idx is not None and option_idx < len(options):
                                    chosen_option = options[option_idx]
                                    success = await l3_manager.resolve_confirmation(
                                        confirmation_id=str(confirmation.get("_id")),
                                        chosen_option=chosen_option,
                                        session_id=session_id
                                    )
                                    
                                    if success and client_active:
                                        if chosen_option == "Ignore":
                                            response_text = "Got it, I won't add that."
                                        else:
                                            node_name = confirmation.get("node_name", "")
                                            response_text = f"Added {node_name} under {chosen_option}"
                                        
                                        # Send as text response
                                        await websocket.send_json({
                                            "type": "transcript",
                                            "text": response_text,
                                            "turn_id": str(uuid.uuid4())
                                        })
                                    logger.info(f"[GRAPH] Confirmation resolved via text: {chosen_option}")
                                    continue
                        except Exception as e:
                            logger.error(f"[GRAPH] Failed to handle text confirmation: {e}")
                    
                    # Block text input during TOOL_EXECUTING
                    if tsm and getattr(tsm, 'state', None) == TurnState.TOOL_EXECUTING:
                        if client_active:
                            await websocket.send_json({"type": "warning", "message": "Still executing tool — I'll handle this right after."})
                        continue
                    
                    from backend.app.core.rate_limiter import ws_rate_limiter
                    if not ws_rate_limiter.check(session_id or getattr(websocket.client, "host", "unknown")):
                        logger.warning(f"[RateLimit] Rate limit exceeded for {session_id}")
                        if client_active:
                            asyncio.create_task(broadcast_error(websocket, "RateLimit", "Whoa, too fast! Give me a second."))
                        continue
                    
                    if session_context["turn_task"] and not session_context["turn_task"].done():
                        session_context["turn_task"].cancel()
                        session_context["turn_task"] = None
                    
                    audio_buffer = bytearray() # Clear any audio
                    session_context["turn_task"] = TaskRegistry.track(
                        process_turn(transcript_override=text),
                        name=f"process_turn_text:{session_id[:8] if session_id else 'unknown'}",
                        session_id=session_id,
                    )
    except Exception as e:
        logger.error(f"[WS] Critical Connection Error: {e}")
    finally:
        client_active = False # Ensure no residual tasks push messages
        _active_connections.discard(websocket)
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
