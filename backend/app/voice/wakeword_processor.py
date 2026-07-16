import logging
import numpy as np
from pipecat.frames.frames import Frame, AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
import openwakeword
from openwakeword.model import Model

logger = logging.getLogger("WakeWordProcessor")

class ServerWakeWordConfirmProcessor(FrameProcessor):
    """
    Continuous Wake Word Gate: Buffers audio and feeds it to openWakeWord.
    It drops all upstream audio UNTIL it detects 'hey_jarvis'.
    Once detected, it opens the gate and passes all subsequent audio to STT.
    """
    def __init__(self, threshold=0.5, sample_rate=16000):
        super().__init__()
        self.threshold = threshold
        self.sample_rate = sample_rate
        
        self.has_confirmed = False
        
        openwakeword.utils.download_models()
        self.oww_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        # We only intercept incoming raw audio from the user
        if direction == FrameDirection.UPSTREAM and isinstance(frame, AudioRawFrame) and not self.has_confirmed:
            # Convert bytes to numpy array for openwakeword
            audio_np = np.frombuffer(frame.audio, dtype=np.int16)
            
            # Predict continuously maintains state
            prediction = self.oww_model.predict(audio_np)
            
            score = prediction.get("hey_jarvis", 0.0)
            
            if score >= self.threshold:
                self.has_confirmed = True
                logger.info(f"[WakeWordConfirm] WAKE WORD DETECTED! Score: {score:.3f}. Opening gate.")
                # Pass the frame that triggered it downstream so VAD/STT catches the start of speech
                await self.push_frame(frame, direction)
            
            # Drop the frame (don't push downstream) until confirmed
            return

        # Default behavior: pass through (either we already confirmed or it's a different frame type/direction)
        await self.push_frame(frame, direction)
