import logging
import numpy as np
from pipecat.frames.frames import Frame, AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
import openwakeword
from openwakeword.model import Model

from backend.app.config import settings

logger = logging.getLogger("WakeWordProcessor")


class ServerWakeWordConfirmProcessor(FrameProcessor):
    """
    Continuous Wake Word Gate: Buffers audio and feeds it to openWakeWord.
    It drops all upstream audio UNTIL it detects the configured wake word model.
    Once detected, it opens the gate and passes all subsequent audio to STT.
    """
    def __init__(self, threshold=0.5, sample_rate=16000, wake_word_models: list[str] | None = None):
        super().__init__()
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.wake_word_models = wake_word_models or [
            m.strip() for m in settings.WAKE_WORD_MODELS.split(",") if m.strip()
        ]
        if not self.wake_word_models:
            self.wake_word_models = ["hey_asta"]

        self.has_confirmed = False

        openwakeword.utils.download_models()
        self.oww_model = Model(wakeword_models=self.wake_word_models, inference_framework="onnx")

    def _best_score(self, prediction: dict) -> float:
        return max(prediction.get(m, 0.0) for m in self.wake_word_models)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # We only intercept incoming raw audio from the user
        if direction == FrameDirection.UPSTREAM and isinstance(frame, AudioRawFrame) and not self.has_confirmed:
            audio_np = np.frombuffer(frame.audio, dtype=np.int16)
            prediction = self.oww_model.predict(audio_np)
            score = self._best_score(prediction)

            if score >= self.threshold:
                self.has_confirmed = True
                logger.info(f"[WakeWordConfirm] WAKE WORD DETECTED! Score: {score:.3f}. Opening gate.")
                await self.push_frame(frame, direction)

            return

        await self.push_frame(frame, direction)
