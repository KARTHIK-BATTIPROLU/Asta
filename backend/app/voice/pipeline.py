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
from backend.app.core.llm_factory import router

logger = logging.getLogger("Pipeline")

class RouterLLMService(LLMService):
    def __init__(self, task: str = "realtime_chat"):
        super().__init__()
        self.task = task
        self.messages = []

    async def process_frame(self, frame: Frame, direction):
        if isinstance(frame, TranscriptionFrame):
            self.messages.append({"role": "user", "content": frame.text})
            
            await self.push_frame(LLMFullResponseStartFrame(), direction)
            
            try:
                # In a real streaming implementation, Router needs to yield chunks.
                # For Phase 1 initial setup, we do a blocking complete and yield one TextFrame
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

def build_pipeline(transport):
    vad = SileroVADAnalyzer()
    
    pipeline = Pipeline([
        transport.input(),
        vad,
        GroqWhisperSTT(),
        ReflexProcessor(),
        # MemoryContextInjector(), # Add in Phase 3
        RouterLLMService(task="realtime_chat"),
        SentenceAggregator(),
        LanguageSplitTTS(),
        transport.output(),
    ])
    
    return pipeline
