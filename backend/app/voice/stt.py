import os
import logging
from typing import AsyncGenerator
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.services.stt_service import STTService
from backend.app.core.llm_factory import router

logger = logging.getLogger("GroqWhisperSTT")

def vocab_bias_string() -> str:
    # In a real app this would load from prompts/stt_vocab.md
    return "ASTA, Karthik, Notion, Neo4j, DSA, Pipecat"

class GroqWhisperSTT(STTService):
    def __init__(self, vocab_bias: str = ""):
        super().__init__()
        self.vocab_bias = vocab_bias or vocab_bias_string()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        try:
            text = await router.run("stt", audio=audio,
                                    prompt=self.vocab_bias,
                                    language=None)
            if not text or not text.strip():
                return
            # We don't have exact language detection from the simplistic API currently, default to 'en'
            yield TranscriptionFrame(text, user_id="user", timestamp=0.0)
        except Exception as e:
            logger.error(f"STT failed: {e}")
