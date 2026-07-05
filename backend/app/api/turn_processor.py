import asyncio
import logging
import uuid
import struct
import base64
import json
import re
from fastapi import WebSocket
from backend.app.services.stt_service import transcribe_audio
from backend.app.services.llm_service import stream_llm_response
from backend.app.services.l1_cache import l1_manager
from backend.app.core.circuit_breaker import status_registry
from backend.app.speech.deepgram_stream import DeepgramStreamService
from backend.app.services.llm_hardening import sanitize_input
from backend.app.core.turn_state import TurnStateMachine, TurnState
from backend.app.models.action_model import ActionRequest
from backend.app.core.task_registry import TaskRegistry
from backend.app.api.tool_forcing import check_tool_forcing
from backend.app.services.tts_service import synthesize_speech_stream
import websockets

logger = logging.getLogger("TurnProcessor")

class TurnContext:
    def __init__(self, websocket, redis_pool):
        self.websocket = websocket
        self.redis_pool = redis_pool
        self.session_id = None
        self.client_active = True
        self.stt_stream = None
        self.stt_stream_ready = False
        self.stt_connect_task = None
        self.tsm = None
        self.session_context = {
            "turn_task": None,
            "tts_worker_task": None
        }

async def broadcast_error(websocket: WebSocket, error_type: str, message: str):
    """Send error to frontend and log. Used for TTS timeout handling."""
    try:
        await websocket.send_json({"type": "error", "message": message})
        logger.error(f"[TTS] {error_type}: {message}")
    except Exception as e:
        logger.error(f"[broadcast_error] Failed to send: {e}")

async def _speak_text(websocket: WebSocket, text: str, turn_id: str, session_id: str,
                       redis_pool, tsm: "TurnStateMachine | None" = None):
    """Stream TTS audio for `text` using the same wire format as the live-chat
    path (4-byte seq_id header + linear16 PCM, base64-encoded `audio` frames),
    so the client's existing PCMPlayer can play it unmodified."""
    text = (text or "").strip()
    if not text:
        return

    from backend.app.api.settings_routes import is_silent_mode
    if await is_silent_mode(session_id):
        logger.info(f"[TTS] Silent mode active. Bypassing speech for session {session_id}")
        return

    seq_id = 0
    if session_id and redis_pool:
        try:
            seq_str = await redis_pool.hget(f"asta:session:{session_id}", "sequence_id")
            seq_id = int(seq_str) if seq_str else 0
        except Exception:
            pass

    try:
        first_chunk = True
        async for pcm_chunk in synthesize_speech_stream(text):
            if first_chunk:
                first_chunk = False
                if tsm is not None and tsm.state not in (TurnState.SPEAKING, TurnState.IDLE):
                    try:
                        await tsm.transition(TurnState.SPEAKING)
                    except Exception:
                        pass
                try:
                    await websocket.send_json({"type": "status", "status": "speaking", "turn_id": turn_id})
                except Exception:
                    pass
            seq_header = struct.pack(">I", seq_id)
            encoded = base64.b64encode(seq_header + pcm_chunk).decode("utf-8")
            try:
                await websocket.send_json({"type": "audio", "data": encoded})
            except Exception:
                break
    except Exception as e:
        logger.warning(f"[TTS] _speak_text failed: {e}")

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
                    await l1_manager.get_session(session_id).set_speculative_data(f"tool_result_{tool_name}", None)
            
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



class TurnProcessor:
    def __init__(self, ctx: TurnContext):
        self.ctx = ctx
        
        async def process_turn(audio_data=None, transcript_override=None):
            
            if not self.ctx.client_active:
                return
            
            current_turn_id = str(uuid.uuid4())
            
            if not self.ctx.tsm or self.ctx.tsm.turn_id != current_turn_id:
                from backend.app.core.turn_state import TurnStateMachine, TurnState
                self.ctx.tsm = TurnStateMachine(self.ctx.session_id or "unknown", current_turn_id)
                await self.ctx.tsm.transition(TurnState.LISTENING)
                
            if self.ctx.session_id and self.ctx.redis_pool:
                try:
                    await self.ctx.redis_pool.hset(f"asta:session:{self.ctx.session_id}", "current_turn_id", current_turn_id)
                except Exception as e:
                    logger.error(f"[WS] Redis error during process_turn hset: {e}")
    
            try:
                if audio_data:
                    logger.info(f"[TURN] Processing {len(audio_data)} bytes of audio")
                
                await self.ctx.tsm.transition(TurnState.PROCESSING)
                
                if self.ctx.client_active:
                    await self.ctx.websocket.send_json({"type": "status", "status": "processing", "turn_id": current_turn_id})
                
                if transcript_override is not None:
                    transcript = transcript_override
                else:
                    if self.ctx.stt_connect_task and not self.ctx.stt_connect_task.done():
                        logger.info("[STT L1.5] Turn ended before connect finished, bypassing to REST API")
                        self.ctx.stt_connect_task.cancel()
                        self.ctx.stt_connect_task = None
                        self.ctx.stt_stream = None
                        self.ctx.stt_stream_ready = False
    
                    if isinstance(self.ctx.stt_stream, DeepgramStreamService) and self.ctx.stt_stream.is_stream_active:
                        stt_result = await self.ctx.stt_stream.finish()
                        transcript = stt_result.get("text", "")
                        self.ctx.stt_stream = None # Reset for next turn
                        self.ctx.stt_stream_ready = False
                    else:
                        transcript = await transcribe_audio(audio_data)
                    
                if not transcript or not transcript.strip():
                    if self.ctx.tsm.state != TurnState.IDLE:
                        await self.ctx.tsm.transition(TurnState.IDLE)
                    if self.ctx.client_active:
                        await self.ctx.websocket.send_json({"type": "status", "status": "listening", "turn_id": current_turn_id})
                    return
    
                # SECURITY: Sanitize transcript against prompt injection attacks
                transcript = sanitize_input(transcript)
    
                if self.ctx.client_active:
                    await self.ctx.websocket.send_json({"type": "transcript", "text": transcript, "turn_id": current_turn_id})
    
                async def stream_parallel_turn():
                    import websockets
                    import base64
                    from backend.app.config import config as settings
                    from backend.app.services.intent_detector import intent_detector
                    import struct
                    
                    await self.ctx.tsm.transition(TurnState.THINKING)
                    
                    if self.ctx.client_active:
                        await self.ctx.websocket.send_json({"type": "status", "status": "thinking", "turn_id": current_turn_id})
    
                    # INTENT DETECTION - Route based on user intent
                    intent = intent_detector.detect(transcript)
                    logger.info(f"[INTENT] Detected: {intent['type']} (confidence={intent['confidence']:.2f}) - {intent['reasoning']}")
                    
                    # Fetch memory context based on intent
                    skip_rag = intent_detector.should_skip_rag(intent)
                    mem_task = asyncio.create_task(fetch_memory_context(transcript, self.ctx.session_id, skip_rag=skip_rag))
                    history, rag_context = None, None
                    
                    if self.ctx.session_id:
                        history = l1_manager.get_session(self.ctx.session_id).get_llm_history()
                        
                    try:
                        _, rag_context = await asyncio.wait_for(asyncio.shield(mem_task), timeout=10.0)
                    except asyncio.TimeoutError:
                        logger.warning("[MEMORY] Context injection missed 10.0s window. Using history only.")
    
                    if not self.ctx.client_active:
                        return
    
                    # Get forced tool from intent detector first
                    forced_tool = intent_detector.get_forced_tool(intent)
    
                    # A thread paused on a clarification (interrupt()) or mid content
                    # review (content_state.phase=="awaiting_review") must always
                    # resume through the supervisor, regardless of this turn's
                    # keywords — otherwise the reply gets stranded in plain chat.
                    from backend.app.core.supervisor_graph import is_awaiting_resume, ROUTINE_KEYWORDS, CONTENT_KEYWORDS
                    session_paused = await is_awaiting_resume(self.ctx.session_id)
    
                    # Check if we should route to supervisor for workflow execution
                    # Notion, routine, research, and content intents should use workflows.
                    # ROUTINE_KEYWORDS/CONTENT_KEYWORDS mirror classify_intent's own fast
                    # paths so this pre-classification stays in sync with the supervisor's.
                    workflow_keywords = ["notion", "task", "routine", "research", "linkedin", "content", "morning", "night", "plan"]
                    should_use_workflow = (
                        session_paused or
                        forced_tool == "notion" or
                        intent['type'] in ['routine', 'research', 'content'] or
                        any(kw in transcript.lower() for kw in workflow_keywords + ROUTINE_KEYWORDS + CONTENT_KEYWORDS)
                    )
                    
                    if should_use_workflow:
                        logger.info(f"[WORKFLOW] Routing to supervisor for workflow execution")
                        
                        try:
                            from backend.app.core.supervisor_graph import run_supervisor_graph
                            from backend.app.core.llm_factory import acomplete
    
                            # Run supervisor graph (it classifies + routes internally)
                            await self.ctx.tsm.transition(TurnState.TOOL_PENDING)
                            await self.ctx.tsm.transition(TurnState.TOOL_EXECUTING)
                            
                            # 1. Handle Morning Alarm Awake Verification State Machine
                            from backend.app.workflows import awake_verification
                            
                            if transcript.startswith("[MORNING ALARM TRIGGER]"):
                                # Parse lat/lon if available
                                lat, lon = None, None
                                if "lat:" in transcript and "lon:" in transcript:
                                    try:
                                        parts = transcript.split("lat:")[1].split(", lon:")
                                        lat = float(parts[0].strip())
                                        lon = float(parts[1].strip())
                                    except Exception:
                                        pass
                                
                                # Initial trigger from WakeUpActivity
                                result = await awake_verification.start_verification(self.ctx.session_id, lat=lat, lon=lon)
                                response_text = result["prompt"]
                                awaiting_clarification = True
                                task_data = {"status": result["status"]}
                                logger.info("[AWAKE] Started verification loop")
                            
                            elif awake_verification.has_active_verification(self.ctx.session_id):
                                # Subsequent turns while verification is active
                                result = await awake_verification.advance_verification(self.ctx.session_id, transcript)
                                response_text = result["prompt"]
                                
                                if result["status"] == "awake":
                                    awaiting_clarification = False
                                    task_data = {"status": "awake", "action": "run_briefing"}
                                    logger.info("[AWAKE] User verified awake! Generating Morning Briefing...")
                                    try:
                                        from backend.app.workflows.routine_engine import RoutineEngine
                                        # Extract coordinates
                                        wake_lat = result.get("lat")
                                        wake_lon = result.get("lon")
                                        # Generate the full briefing text via LLM and tool aggregation
                                        briefing_text = await RoutineEngine().run_morning_routine(user_city="Bangalore", session_id=self.ctx.session_id, lat=wake_lat, lon=wake_lon)
                                        response_text = result["prompt"] + "\n\n" + briefing_text
                                    except Exception as e:
                                        logger.error(f"[AWAKE] Failed to generate briefing: {e}")
                                        response_text = result["prompt"] + " Actually, I'm having trouble pulling up your briefing right now. But the important thing is you're awake!"
                                elif result["status"] == "snoozing":
                                    awaiting_clarification = False
                                    task_data = {"status": "snoozing", "action": "set_snooze", "minutes": result.get("minutes", 10)}
                                    logger.info("[AWAKE] User snoozed")
                                else:
                                    awaiting_clarification = True
                                    task_data = {"status": "verifying"}
                                    logger.info("[AWAKE] Verification ongoing...")
    
                            else:
                                try:
                                    await self.ctx.websocket.send_json({"type": "llm_chunk", "text": "Let me check that for you, boss...\n", "turn_id": current_turn_id})
                                except Exception:
                                    pass
    
                                # Execute supervisor graph
                                result = await asyncio.wait_for(
                                    run_supervisor_graph(
                                        session_id=self.ctx.session_id,
                                        user_input=transcript,
                                        messages=(history or []),
                                    ),
                                    timeout=60.0
                                )
    
                                await self.ctx.tsm.resolve_tool(result)
    
                                # Get response from supervisor (graph returns "response")
                                response_text = result.get("response") or result.get("asta_response", "Task completed.")
                                awaiting_clarification = bool(result.get("awaiting_clarification"))
                                task_data = result.get("task_data") or {}
                                logger.info(f"[WORKFLOW] Supervisor completed: intent={result.get('intent', 'unknown')}")
    
                            # Stream full response text to client (UI history, unchanged)
                            try:
                                chunk_size = 50
                                for i in range(0, len(response_text), chunk_size):
                                    chunk = response_text[i:i+chunk_size]
                                    await self.ctx.websocket.send_json({"type": "llm_chunk", "text": chunk, "turn_id": current_turn_id})
                                    await asyncio.sleep(0.05)  # Small delay for streaming effect
                            except Exception:
                                pass
    
                            # Surface structured results (drafts/images/Notion links,
                            # or a pending clarification) for the UI to render.
                            task_data = result.get("task_data") or {}
                            if task_data or awaiting_clarification:
                                try:
                                    await self.ctx.websocket.send_json({
                                        "type": "workflow_result",
                                        "intent": result.get("intent", ""),
                                        "task_data": task_data,
                                        "awaiting_clarification": awaiting_clarification,
                                        "turn_id": current_turn_id,
                                    })
                                except Exception:
                                    pass
    
                            # TTS: speak clarifying questions verbatim (the user must
                            # answer them); summarize long results into 1-2 spoken
                            # sentences so the read-aloud doesn't drone on.
                            voice_text = response_text
                            if not awaiting_clarification and len(response_text) > 280:
                                try:
                                    voice_text = await acomplete(
                                        system=(
                                            "Summarize this for ASTA to SAY OUT LOUD to Karthik (call him "
                                            "'boss'). 1-2 short spoken sentences, keep key facts/numbers, "
                                            "no markdown, no lists, no preamble. Output ONLY the spoken summary."
                                        ),
                                        user=response_text[:2500],
                                        task="quick", temperature=0.3, max_tokens=80,
                                    )
                                    voice_text = (voice_text or "").strip().strip('"') or response_text[:280]
                                except Exception as sum_err:
                                    logger.debug(f"[WORKFLOW] voice summary skipped: {sum_err}")
                                    voice_text = response_text[:280]
    
                            try:
                                await _speak_text(self.ctx.websocket, voice_text, current_turn_id, self.ctx.session_id, self.ctx.redis_pool, self.ctx.tsm)
                            except Exception as tts_err:
                                logger.warning(f"[WORKFLOW] TTS synthesis failed: {tts_err}")
    
                            try:
                                await self.ctx.websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                            except Exception:
                                pass
    
                            # Save to session
                            if self.ctx.session_id:
                                await l1_manager.get_session(self.ctx.session_id).append_turn(transcript, response_text)
                                try:
                                    from backend.app.services.session_manager import SessionManager
                                    await SessionManager.add_message(self.ctx.session_id, "user", transcript)
                                    await SessionManager.add_message(self.ctx.session_id, "assistant", response_text)
                                except Exception as e:
                                    logger.error(f"[WS] Error saving workflow messages: {e}")
                            
                            await self.ctx.tsm.transition(TurnState.IDLE)
                            return  # Exit early, workflow handled everything
                            
                        except asyncio.TimeoutError:
                            logger.error("[WORKFLOW] Supervisor execution timed out")
                            await self.ctx.tsm.fail_tool("Workflow execution timed out")
                            error_msg = "Sorry boss, that took too long. Let me try a different approach."
                            try:
                                await self.ctx.websocket.send_json({"type": "llm_chunk", "text": error_msg, "turn_id": current_turn_id})
                            except Exception:
                                pass
                            # Fall through to regular LLM
                        except Exception as workflow_err:
                            logger.error(f"[WORKFLOW] Supervisor execution failed: {workflow_err}", exc_info=True)
                            await self.ctx.tsm.fail_tool(str(workflow_err))
                            # Fall through to regular LLM to explain the error
                    
                    # Check if we should force a tool call (for non-workflow tools)
                    tool_payload = check_tool_forcing(transcript, intent, forced_tool, should_use_workflow)
                    
                    if tool_payload and tool_payload.get("tool") == "study_planner":
                        from backend.app.workflows import study_planner
    
                        await self.ctx.tsm.transition(TurnState.TOOL_PENDING)
                        await self.ctx.tsm.transition(TurnState.TOOL_EXECUTING)

                        try:
                            await self.ctx.websocket.send_json({"type": "llm_chunk", "text": "[Study Planner]\n", "turn_id": current_turn_id})
                        except Exception:
                            pass

                        try:
                            if study_planner.has_active_intake(self.ctx.session_id):
                                result = await study_planner.advance_intake(self.ctx.session_id, transcript)
                            elif any(kw in transcript.lower() for kw in ["today", "what am i", "what should i", "my plan"]):
                                result = await study_planner.get_today_plan(self.ctx.session_id)
                            else:
                                result = await study_planner.run_intake(self.ctx.session_id, mode="voice")

                            if "prompt" in result:
                                result_text = result["prompt"]
                            elif "summary" in result:
                                result_text = result["summary"]
                            else:
                                result_text = str(result)

                            try:
                                await self.ctx.websocket.send_json({"type": "llm_chunk", "text": result_text, "turn_id": current_turn_id})
                                await self.ctx.websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                            except Exception:
                                pass

                            await self.ctx.tsm.resolve_tool(None)
                            logger.info(f"[INTENT] Study planner flow completed: {result.get('stage', 'unknown')}")
                        except Exception as sp_err:
                            logger.error(f"[INTENT] Study planner error: {sp_err}", exc_info=True)
                            await self.ctx.tsm.fail_tool(str(sp_err))
                            try:
                                await self.ctx.websocket.send_json({"type": "llm_chunk", "text": f"Study planner error: {sp_err}", "turn_id": current_turn_id})
                            except Exception:
                                pass
                        return

                        # If we have a tool payload, execute it directly
                        if tool_payload:
                            from backend.app.services.action_executor import action_executor
                            
                            await self.ctx.tsm.transition(TurnState.TOOL_PENDING)
                            await self.ctx.tsm.transition(TurnState.TOOL_EXECUTING)
                            
                            try:
                                await self.ctx.websocket.send_json({"type": "llm_chunk", "text": f"[Checking {forced_tool}...]\n", "turn_id": current_turn_id})
                            except Exception:
                                pass
                            
                            try:
                                req = ActionRequest(
                                    session_id=self.ctx.session_id,
                                    tool_name=forced_tool,
                                    parameters=tool_payload,
                                    intent=tool_payload.get("intent", ""),
                                    memory_tag=tool_payload.get("memory_tag", ""),
                                )
                                
                                await self.ctx.tsm.dispatch_tool(forced_tool, tool_payload)
                                
                                tool_result = await asyncio.wait_for(
                                    action_executor.execute_action(req),
                                    timeout=65.0
                                )
                                await self.ctx.tsm.resolve_tool(tool_result)
                                logger.info(f"[INTENT] Forced tool completed: {tool_result.tool_name} -> {tool_result.status}")
                                
                                # Send tool result as response
                                result_text = str(tool_result.result)[:1000]
                                
                                try:
                                    await self.ctx.websocket.send_json({"type": "llm_chunk", "text": result_text, "turn_id": current_turn_id})
                                    await self.ctx.websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                                except Exception:
                                    pass
                                
                                # Save to session
                                if self.ctx.session_id:
                                    await self.ctx.tsm.transition(TurnState.IDLE)
                                    await l1_manager.get_session(self.ctx.session_id).append_turn(transcript, result_text)
                                    try:
                                        from backend.app.services.session_manager import SessionManager
                                        await SessionManager.add_message(self.ctx.session_id, "user", transcript)
                                        await SessionManager.add_message(self.ctx.session_id, "assistant", result_text)
                                    except Exception as e:
                                        logger.error(f"[WS] Error saving forced tool messages: {e}")
                                    
                                    await self.ctx.tsm.transition(TurnState.IDLE)
                                
                                return  # Exit early, tool handled everything
                                
                            except Exception as tool_err:
                                logger.error(f"[INTENT] Forced tool execution failed: {tool_err}")
                                await self.ctx.tsm.fail_tool(str(tool_err))
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
                            if self.ctx.session_id:
                                try:
                                    from backend.app.services.session_manager import SessionManager
                                    _sess = await SessionManager.get_session(self.ctx.session_id)
                                    if _sess:
                                        session_memory_context = getattr(_sess, "memory_context", "") or ""
                                except Exception:
                                    pass
                            
                            is_json_tool_call = False
                            json_buffer = ""
                            has_started_tts = False
                            
                            async for text_chunk in stream_llm_response(transcript, self.ctx.session_id, history, rag_context, health_status=memory_mode, memory_context=session_memory_context):
                                if not self.ctx.client_active: break
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
                                        await self.ctx.websocket.send_json({"type": "llm_chunk", "text": text_chunk, "turn_id": current_turn_id})
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        await self.ctx.websocket.send_json({"type": "llm_chunk", "text": text_chunk, "turn_id": current_turn_id})
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
    
                                        await self.ctx.tsm.transition(TurnState.TOOL_PENDING)
                                        await self.ctx.tsm.transition(TurnState.TOOL_EXECUTING)
    
                                        await self.ctx.websocket.send_json({"type": "llm_chunk", "text": "\n[Executing Tool...]", "turn_id": current_turn_id})
                                        await token_queue.put("Executing autonomous protocol. Keep the comms open.")
    
                                        resolved_tool = tool_payload.get("tool") or tool_payload.get("action")
                                        await self.ctx.tsm.dispatch_tool(resolved_tool, tool_payload)
    
                                        try:
                                            req = ActionRequest(
                                                session_id=self.ctx.session_id,
                                                tool_name=resolved_tool,
                                                parameters=tool_payload,
                                                intent=tool_payload.get("intent", ""),
                                                memory_tag=tool_payload.get("memory_tag", ""),
                                            )
                                        except Exception as validation_err:
                                            logger.error(f"[WS] Tool payload validation failed: {validation_err}")
                                            await token_queue.put(f"Security block. Payload rejected: {validation_err}")
                                            await self.ctx.tsm.fail_tool(str(validation_err))
                                            raise
                                        
                                        # BLOCKING AWAIT — do NOT fire-and-forget.
                                        # Turn finalization waits for tool result.
                                        try:
                                            tool_result = await asyncio.wait_for(
                                                action_executor.execute_action(req),
                                                timeout=65.0  # Slightly above executor's internal 60s timeout
                                            )
                                            await self.ctx.tsm.resolve_tool(tool_result)
                                            logger.info(f"[WS] Tool completed: {tool_result.tool_name} -> {tool_result.status}")
                                            
                                            # Inject tool result into TTS so user hears the outcome
                                            result_summary = tool_result.result[:500]
                                            await token_queue.put(f" Tool completed. {result_summary}")
                                            
                                        except asyncio.TimeoutError:
                                            await self.ctx.tsm.fail_tool("Tool execution timed out.")
                                            await token_queue.put("Tool execution timed out. Report this to Karthik.")
                                            logger.error(f"[WS] Tool execution timed out for {tool_payload.get('tool')}")
                                        except Exception as exec_err:
                                            await self.ctx.tsm.fail_tool(str(exec_err))
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
                                
                            if self.ctx.client_active:
                                try:
                                    await self.ctx.websocket.send_json({"type": "error", "message": error_message})
                                    await token_queue.put(error_message)
                                except Exception as err_err:
                                    logger.error(f"[LLM] Failed to send error message: {err_err}")
                        finally:
                            await token_queue.put(None)
    
                    async def deepgram_pusher(dg_ws):
                        try:
                            text_buffer = ""
                            while self.ctx.client_active:
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
                            logger.warning(f"[DG] TTS self.ctx.websocket sent close: {e}")
                            if self.ctx.client_active:
                                await broadcast_error(self.ctx.websocket, "TTS_TIMEOUT", "TTS service connection lost. Please try again.")
                        except Exception as e:
                            logger.error(f"[DG] Pusher failed: {e}")
                            if self.ctx.client_active:
                                await broadcast_error(self.ctx.websocket, "TTS_ERROR", f"TTS service error: {e}")
    
                    async def client_pusher(dg_ws):
                        seq_id = 0
                        if self.ctx.session_id and self.ctx.redis_pool:
                            try:
                                seq_str = await self.ctx.redis_pool.hget(f"asta:session:{self.ctx.session_id}", "sequence_id")
                                seq_id = int(seq_str) if seq_str else 0
                            except Exception:
                                pass
                                
                        try:
                            first_chunk = True
                            while self.ctx.client_active:
                                msg = await dg_ws.recv()
                                if isinstance(msg, bytes):
                                    if first_chunk:
                                        first_chunk = False
                                        try:
                                            if self.ctx.tsm.state not in {TurnState.SPEAKING, TurnState.IDLE}:
                                                await self.ctx.tsm.transition(TurnState.SPEAKING)
                                            await self.ctx.websocket.send_json({"type": "status", "status": "speaking", "turn_id": current_turn_id})
                                        except Exception: pass
                                        
                                    seq_header = struct.pack(">I", seq_id)
                                    combined = seq_header + msg
                                    encoded = base64.b64encode(combined).decode("utf-8")
                                    
                                    try:
                                        await self.ctx.websocket.send_json({
                                            "type": "audio",
                                            "data": encoded
                                        })
                                    except Exception: pass
                                elif isinstance(msg, str):
                                    data = json.loads(msg)
                                    if data.get("type") == "Flushed" or data.get("type") == "Warning":
                                        pass
                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"[CLI] TTS self.ctx.websocket closed early: {e}")
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
                            
                            self.ctx.session_context["tts_worker_task"] = task_c
                            
                            await asyncio.gather(task_a, task_b, task_c)
                    except Exception as ws_err:
                        import traceback
                        logger.error(f"[WS] Error connecting to Deepgram TTS: {ws_err}\n{traceback.format_exc()}")
                        # Since Deepgram failed, block and await the LLM task so text generation continues back to user
                        await task_a
    
                    final_text = "".join(full_response)
                    logger.info(f"[TURN] LLM & TTS complete: '{final_text[:80]}...'")
                    
                    try:
                        if self.ctx.client_active:
                            await self.ctx.websocket.send_json({"type": "audio_end", "turn_id": current_turn_id})
                    except Exception:
                        pass
                    
                    if self.ctx.session_id:
                        # Transition to IDLE after completing response
                        await self.ctx.tsm.transition(TurnState.IDLE)
                        # Commit user message
                        await l1_manager.get_session(self.ctx.session_id).append_turn(transcript, final_text)
                        try:
                            from backend.app.services.session_manager import SessionManager
                            await SessionManager.add_message(self.ctx.session_id, "user", transcript)
                            await SessionManager.add_message(self.ctx.session_id, "assistant", final_text)
                            
                            # MEMORY COMMIT: If a tool executed, commit the result as a first-class message
                            # This ensures tool output persists through L1 → L2 → L3 propagation
                            if self.ctx.tsm.has_tool_result and getattr(self.ctx.tsm.tool_result, 'status', None) == "success":
                                tool_result_msg = self.ctx.tsm.format_tool_result_tag()
                                await SessionManager.add_message(self.ctx.session_id, "assistant", tool_result_msg)
                                # Also commit to L1 so subsequent turns in this session can reference it
                                l1_session = l1_manager.get_session(self.ctx.session_id)
                                if l1_session:
                                    # Add the specific tool logic
                                    await l1_session.set_speculative_data(f"tool_result_{self.ctx.tsm.tool_name}", {
                                        "tool": self.ctx.tsm.tool_name,
                                        "status": getattr(self.ctx.tsm.tool_result, 'status', "success"),
                                        "data": str(self.ctx.tsm.tool_result.result) if hasattr(self.ctx.tsm.tool_result, 'result') else str(self.ctx.tsm.tool_result),
                                        "intent": getattr(self.ctx.tsm.tool_result, 'intent', ""),
                                        "memory_tag": getattr(self.ctx.tsm.tool_result, 'memory_tag', ""),
                                    })
                                logger.info(f"[MEMORY_COMMIT] Tool result committed to session: {self.ctx.tsm.tool_name}")
                        except Exception as e:
                            logger.error(f"[WS] Error saving messages to SessionManager: {e}")
                        
    
                        
                        finally:
                            # Transition to IDLE for next turn (already IDLE if the
                            # transition above at line ~992 ran without error)
                            if self.ctx.tsm.state != TurnState.IDLE:
                                await self.ctx.tsm.transition(TurnState.IDLE)
    
                # Execute the parallel turn
                await stream_parallel_turn()
            except asyncio.CancelledError:
                logger.info("[TURN] Cancelled by user (abort)")
            except Exception as e:
                logger.error(f"[TURN] Error: {type(e).__name__}: {e}")
                try:
                    if self.ctx.client_active:
                        await self.ctx.websocket.send_json({"type": "error", "message": f"Processing fail: {e}"})
                except Exception:
                    pass
    
