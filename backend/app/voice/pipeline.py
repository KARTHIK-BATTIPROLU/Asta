import logging
from typing import AsyncGenerator
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.services.llm_service import LLMService
from pipecat.services.tts_service import TTSService
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame
from pipecat.audio.vad.silero import SileroVADAnalyzer

from backend.app.voice.stt import GroqWhisperSTT
from backend.app.voice.reflex import ReflexProcessor
from backend.app.voice.wakeword_processor import ServerWakeWordConfirmProcessor
from backend.app.voice.memory_injector import MemoryContextInjector, SystemPromptUpdateFrame
from backend.app.core.llm_factory import router

logger = logging.getLogger("Pipeline")

class RouterLLMService(LLMService):
    def __init__(self, task: str = "realtime_chat", trigger: str = "manual"):
        super().__init__()
        self.task = task
        self.trigger = trigger
        self.messages = []
        self._morning_injected = False

    async def process_frame(self, frame: Frame, direction):
        if isinstance(frame, SystemPromptUpdateFrame):
            # Update the system prompt in the messages block
            # We assume the first message is the system prompt. If not, insert one.
            if len(self.messages) > 0 and self.messages[0]["role"] == "system":
                self.messages[0]["content"] = frame.system_prompt
            else:
                self.messages.insert(0, {"role": "system", "content": frame.system_prompt})
            logger.info("[RouterLLMService] Updated system prompt with dynamic memory context.")
            
        elif isinstance(frame, TranscriptionFrame):
            self.messages.append({"role": "user", "content": frame.text})
            
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
            user_text_lower = frame.text.lower()
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
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(res_text), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
                return

            await self.push_frame(LLMFullResponseStartFrame(), direction)
            
            try:
                res = await router.run(self.task, self.messages, temperature=0.7)
                self.messages.append({"role": "assistant", "content": res.text})
                await self.push_frame(TextFrame(res.text), direction)
            except Exception as e:
                logger.error(f"RouterLLMService failed: {e}")
                err = "I am experiencing network issues."
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
        except ImportError:
            self.fallback = None

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        # Detect language logic goes here. For now, route to edge-tts.
        if self.fallback:
            async for frame in self.fallback.run_tts(text):
                yield frame

def build_pipeline(transport, trigger="manual"):
    vad = SileroVADAnalyzer()
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
        stt,
        reflex,
        memory_injector,
        RouterLLMService(task="realtime_chat", trigger=trigger),
        aggregator,
        tts,
        transport.output(),
    ])
    
    pipeline = Pipeline(processors)
    
    return pipeline
