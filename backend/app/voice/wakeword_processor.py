import logging
import numpy as np
from pipecat.frames.frames import Frame, AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
import openwakeword
from openwakeword.model import Model

logger = logging.getLogger("WakeWordProcessor")

class ServerWakeWordConfirmProcessor(FrameProcessor):
    """
    Two-stage confirm (D31): Buffers the first 1.5 seconds of audio and 
    runs it through openWakeWord at a higher threshold.
    If it passes, lets audio flow through. If it fails, raises an exception 
    to terminate the pipeline (dropping the false accept silently).
    """
    def __init__(self, threshold=0.6, buffer_duration_sec=1.5, sample_rate=16000):
        super().__init__()
        self.threshold = threshold
        self.sample_rate = sample_rate
        # Buffer enough bytes for the duration (16kHz, 16-bit mono)
        self.target_bytes = int(buffer_duration_sec * sample_rate * 2)
        
        self.audio_buffer = bytearray()
        self.has_confirmed = False
        self.is_failed = False
        
        openwakeword.utils.download_models()
        self.oww_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # We only intercept incoming raw audio from the user
        if direction == FrameDirection.UPSTREAM and isinstance(frame, AudioRawFrame) and not self.has_confirmed:
            if self.is_failed:
                return # Block all further audio

            self.audio_buffer.extend(frame.audio)
            
            if len(self.audio_buffer) >= self.target_bytes:
                # We have enough audio, run inference
                # Copy the buffer to bytes first to avoid locking the bytearray
                audio_np = np.frombuffer(bytes(self.audio_buffer), dtype=np.int16)
                prediction = self.oww_model.predict(audio_np)
                
                # prediction is a dict: {"hey_jarvis": 0.8}
                score = 0.0
                if "hey_jarvis" in prediction:
                    score = prediction["hey_jarvis"]
                    
                logger.info(f"[WakeWordConfirm] Score: {score} (Threshold: {self.threshold})")
                
                if score >= self.threshold:
                    self.has_confirmed = True
                    logger.info("[WakeWordConfirm] PASSED two-stage confirm.")
                    # Flush the buffer downstream so STT doesn't miss the speech!
                    await self.push_frame(AudioRawFrame(audio=bytes(self.audio_buffer), sample_rate=self.sample_rate, num_channels=1))
                    self.audio_buffer.clear()
                else:
                    self.is_failed = True
                    logger.warning("[WakeWordConfirm] FAILED two-stage confirm. Dropping false accept.")
                    # In a real scenario we'd raise a custom exception to cleanly exit Pipecat,
                    # but dropping the frames effectively mutes the user for this session.
                    raise Exception("False Accept Wake Word - Terminating")
            
            return # Do not push frame downstream yet, we are buffering

        # Default behavior: pass through
        await self.push_frame(frame, direction)
