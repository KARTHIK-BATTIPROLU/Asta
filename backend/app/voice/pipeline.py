import logging
from typing import AsyncGenerator
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.services.llm_service import LLMService
from pipecat.services.tts_service import TTSService
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame, VADUserStartedSpeakingFrame
from pipecat.audio.vad.silero import SileroVADAnalyzer

from backend.app.voice.stt import GroqWhisperSTT
from backend.app.voice.reflex import ReflexProcessor
from backend.app.voice.wakeword_processor import ServerWakeWordConfirmProcessor
from backend.app.voice.memory_injector import MemoryContextInjector, SystemPromptUpdateFrame
from backend.app.core.llm_factory import router

logger = logging.getLogger("Pipeline")


async def _emit_orb_state(state: str):
    """Broadcast an orb_state event to connected WS clients. Best-effort --
    a client UI update is never worth failing the pipeline over."""
    try:
        from backend.app.api.ws_transport import broadcast_message
        await broadcast_message({"type": "orb_state", "state": state})
    except Exception as e:
        logger.debug(f"[OrbState] broadcast skipped: {e}")


class VadOrbNotifier(FrameProcessor):
    """
    Sits directly after the VAD stage (before STT has any chance to consume
    VAD's control frames) so it reliably sees VADUserStartedSpeakingFrame --
    pipecat's VADProcessor pushes this unconditionally the moment Silero
    detects speech onset. Translates it into the "listening" orb_state.
    Purely observational: every frame is forwarded downstream unchanged.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStartedSpeakingFrame):
            await _emit_orb_state("listening")
        await self.push_frame(frame, direction)

class RouterLLMService(LLMService):
    def __init__(self, task: str = "realtime_chat", trigger: str = "manual", session_id: str | None = None):
        super().__init__()
        self.task = task
        self.trigger = trigger
        self.session_id = session_id
        self.messages = []
        self._morning_injected = False

    async def process_frame(self, frame: Frame, direction):
        await super().process_frame(frame, direction)
        
        if isinstance(frame, SystemPromptUpdateFrame):
            # Update the system prompt in the messages block
            # We assume the first message is the system prompt. If not, insert one.
            if len(self.messages) > 0 and self.messages[0]["role"] == "system":
                self.messages[0]["content"] = frame.system_prompt
            else:
                self.messages.insert(0, {"role": "system", "content": frame.system_prompt})
            logger.info("[RouterLLMService] Updated system prompt with dynamic memory context.")
            
        elif isinstance(frame, TranscriptionFrame):
            user_text = (frame.text or "").strip()
            user_text_lower = user_text.lower()

            # Private mode commands (simple string match, no LLM)
            if self.session_id and user_text_lower in ("private mode on", "private mode off"):
                from backend.app.voice.session_store import set_private, clear_private, append_turn
                if user_text_lower == "private mode on":
                    await set_private(self.session_id, "no_extract")
                    reply = "Got it — private mode is on. This chat stays between us."
                else:
                    await clear_private(self.session_id)
                    reply = "Private mode off. I'll remember our chats again."
                await append_turn(self.session_id, "user", user_text)
                await append_turn(self.session_id, "assistant", reply)
                await _emit_orb_state("thinking")
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(reply), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
                return

            self.messages.append({"role": "user", "content": frame.text})
            if self.session_id:
                from backend.app.voice.session_store import append_turn
                await append_turn(self.session_id, "user", frame.text)
            await _emit_orb_state("thinking")

            # Inject morning verification on the first turn if trigger is morning_alarm
            if self.trigger == "morning_alarm" and not self._morning_injected:
                from backend.app.services.morning_service import morning_service
                brief = await morning_service.generate_5_minute_brief()
                verification = await morning_service.generate_awake_verification()
                morning_prompt = (
                    f"It's morning time. You just woke Karthik up. First, ask him this verification question:\n"
                    f"\"{verification}\"\n"
                    f"If he gets it right or close enough, give him this brief:\n"
                    f"{brief}\n"
                    f"If he gets it wrong or slurs, give him a math-free challenge (like 'stand up and name three things you must do today')."
                )
                self.messages.insert(0, {"role": "system", "content": morning_prompt})
                self._morning_injected = True

            # Simple intent check for research
            if any(k in user_text_lower for k in ["look into", "research", "deep dive"]):
                logger.info("[RouterLLMService] Research intent detected.")
                # We extract the topic roughly for this simulation
                topic = frame.text
                from backend.app.services.research_service import research_service
                import uuid
                import asyncio
                session_id = str(uuid.uuid4())
                # Spawn background research task
                asyncio.create_task(research_service.run_research(session_id, topic, frame.text))
                
                res_text = "I'm digging into that right now. I'll give you updates as I go."
                if self.session_id:
                    from backend.app.voice.session_store import append_turn
                    await append_turn(self.session_id, "assistant", res_text)
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(res_text), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
                return

            await self.push_frame(LLMFullResponseStartFrame(), direction)
            
            try:
                res = await router.run(self.task, self.messages, temperature=0.7)
                self.messages.append({"role": "assistant", "content": res.text})
                if self.session_id:
                    from backend.app.voice.session_store import append_turn
                    await append_turn(self.session_id, "assistant", res.text)
                await self.push_frame(TextFrame(res.text), direction)
            except Exception as e:
                logger.error(f"RouterLLMService failed: {e}")
                err = "I am experiencing network issues."
                if self.session_id:
                    from backend.app.voice.session_store import append_turn
                    await append_turn(self.session_id, "assistant", err)
                await self.push_frame(TextFrame(err), direction)
                
            await self.push_frame(LLMFullResponseEndFrame(), direction)
        else:
            await self.push_frame(frame, direction)

class LanguageSplitTTS(TTSService):
    def __init__(self):
        super().__init__()
        # Fallback for now to edge-tts since kokoro onnx integration might require custom setup
        try:
            from pipecat.services.edge_tts import EdgeTTSService
            self.fallback = EdgeTTSService(voice="en-US-ChristopherNeural")
        except ImportError as e:
            logger.warning(f"EdgeTTSService not available. TTS will gracefully degrade (no audio). Error: {e}")
            self.fallback = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        logger.info(f"[LanguageSplitTTS] processing frame: {frame.__class__.__name__}")
        if isinstance(frame, TextFrame):
            from backend.app.api.ws_transport import broadcast_message, _active_connections
            logger.info(f"[LanguageSplitTTS] Broadcasting TextFrame text: {frame.text} to {len(_active_connections)} clients")
            await broadcast_message({"type": "text", "text": frame.text})
            
        if isinstance(frame, LLMFullResponseStartFrame):
            await _emit_orb_state("speaking")
            
        if isinstance(frame, LLMFullResponseEndFrame):
            await _emit_orb_state("idle")

        if isinstance(frame, TextFrame) or isinstance(frame, LLMFullResponseEndFrame) or isinstance(frame, LLMFullResponseStartFrame):
            await self.push_frame(frame, direction)
            
        await super().process_frame(frame, direction)

    async def run_tts(self, text: str, context_id: str = "") -> AsyncGenerator[Frame, None]:
        # Detect language logic goes here. For now, route to edge-tts.
        if self.fallback:
            await _emit_orb_state("speaking")
            async for frame in self.fallback.run_tts(text, context_id):
                yield frame
            await _emit_orb_state("idle")

def build_pipeline(transport, trigger="manual", session_id: str | None = None):
    from pipecat.processors.audio.vad_processor import VADProcessor
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer())
    stt = GroqWhisperSTT()
    reflex = ReflexProcessor()
    memory_injector = MemoryContextInjector()
    tts = LanguageSplitTTS()
    aggregator = SentenceAggregator()
    
    processors = [transport.input()]
    
    if trigger == "wake_word":
        wakeword = ServerWakeWordConfirmProcessor(threshold=0.6)
        processors.append(wakeword)
        
    processors.extend([
        vad,
        VadOrbNotifier(),
        stt,
        reflex,
        memory_injector,
        RouterLLMService(task="realtime_chat", trigger=trigger, session_id=session_id),
        aggregator,
        tts,
        transport.output(),
    ])
    
    pipeline = Pipeline(processors)
    
    return pipeline
