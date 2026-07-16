import logging
import numpy as np
from typing import Optional, Callable
import asyncio
from collections import deque

logger = logging.getLogger(__name__)

try:
    from openwakeword.model import Model
    _HAS_OPENWAKEWORD = True
except ImportError:
    Model = None
    _HAS_OPENWAKEWORD = False
    logger.warning("openwakeword not installed; wake word detection disabled")


class WakeWordService:
    """
    Wake word detection service using OpenWakeWord.
    Detects custom wake words like "Hey ASTA" or "ASTA" in audio streams.
    """
    
    def __init__(
        self,
        wake_words: list[str] = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        chunk_size: int = 1280,  # 80ms at 16kHz
        inference_framework: str = "onnx"  # Changed default to onnx
    ):
        """
        Initialize the wake word detection service.
        
        Args:
            wake_words: List of wake word model names to load (e.g., ["hey_asta"])
            threshold: Detection confidence threshold (0.0 to 1.0)
            sample_rate: Audio sample rate in Hz
            chunk_size: Number of samples per chunk (80ms recommended)
            inference_framework: "tflite" or "onnx"
        """
        self.wake_words = wake_words or ["hey_asta"]  # Default wake word
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.inference_framework = inference_framework
        
        self.model: Optional[Model] = None
        self.is_active = False
        self.detection_callback: Optional[Callable] = None
        
        # Audio buffer for accumulating chunks
        self.audio_buffer = deque(maxlen=16)  # Keep last ~1.3 seconds
        
        # Cooldown to prevent multiple detections
        self.cooldown_seconds = 2.0
        self.last_detection_time = 0.0
        
        # Initialize model
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the OpenWakeWord model."""
        if not _HAS_OPENWAKEWORD:
            logger.error("[WakeWord] openwakeword not installed. Install with: pip install openwakeword tflite-runtime")
            return
        
        try:
            # Initialize model with specified wake words
            self.model = Model(
                wakeword_models=self.wake_words,
                inference_framework=self.inference_framework
            )
            self.is_active = True
            logger.info(f"[WakeWord] Initialized with models: {self.wake_words}")
            logger.info(f"[WakeWord] Available models: {list(self.model.models.keys())}")
        except Exception as e:
            logger.error(f"[WakeWord] Failed to initialize model: {e}")
            self.is_active = False
    
    def set_detection_callback(self, callback: Callable):
        """
        Set a callback function to be called when wake word is detected.
        
        Args:
            callback: Async function to call with (wake_word_name, confidence)
        """
        self.detection_callback = callback
    
    def process_audio_chunk(self, audio_chunk: bytes) -> dict:
        """
        Process an audio chunk and detect wake words.
        
        Args:
            audio_chunk: Raw PCM audio data (16-bit, mono)
            
        Returns:
            dict: Detection results with wake word names and confidence scores
        """
        if not self.is_active or not self.model:
            return {}
        
        try:
            # Convert bytes to numpy array (int16)
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # Normalize to float32 [-1.0, 1.0]
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Add to buffer
            self.audio_buffer.append(audio_float)
            
            # Need at least chunk_size samples
            if len(audio_float) < self.chunk_size:
                return {}
            
            # Run prediction
            predictions = self.model.predict(audio_float)
            
            # Check for detections above threshold
            detections = {}
            for wake_word, confidence in predictions.items():
                if confidence >= self.threshold:
                    detections[wake_word] = float(confidence)
                    logger.info(f"[WakeWord] Detected '{wake_word}' with confidence {confidence:.3f}")
            
            return detections
            
        except Exception as e:
            logger.error(f"[WakeWord] Error processing audio: {e}")
            return {}
    
    async def process_audio_stream(self, audio_chunk: bytes) -> Optional[dict]:
        """
        Async wrapper for processing audio chunks with cooldown.
        
        Args:
            audio_chunk: Raw PCM audio data
            
        Returns:
            dict: Detection results if wake word detected, None otherwise
        """
        # Check cooldown
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_detection_time < self.cooldown_seconds:
            return None
        
        detections = self.process_audio_chunk(audio_chunk)
        
        if detections:
            self.last_detection_time = current_time
            
            # Call callback if set
            if self.detection_callback:
                for wake_word, confidence in detections.items():
                    try:
                        if asyncio.iscoroutinefunction(self.detection_callback):
                            await self.detection_callback(wake_word, confidence)
                        else:
                            self.detection_callback(wake_word, confidence)
                    except Exception as e:
                        logger.error(f"[WakeWord] Callback error: {e}")
            
            return detections
        
        return None
    
    def reset(self):
        """Reset the wake word detector state."""
        self.audio_buffer.clear()
        self.last_detection_time = 0.0
        if self.model:
            self.model.reset()
        logger.debug("[WakeWord] State reset")
    
    def set_threshold(self, threshold: float):
        """Update the detection threshold."""
        self.threshold = max(0.0, min(1.0, threshold))
        logger.info(f"[WakeWord] Threshold updated to {self.threshold}")
    
    def set_cooldown(self, seconds: float):
        """Update the cooldown period between detections."""
        self.cooldown_seconds = seconds
        logger.info(f"[WakeWord] Cooldown updated to {seconds}s")
    
    def get_available_models(self) -> list[str]:
        """Get list of available wake word models."""
        if not self.model:
            return []
        return list(self.model.models.keys())
    
    def is_ready(self) -> bool:
        """Check if the wake word service is ready."""
        return self.is_active and self.model is not None


# Global wake word service instance
wake_word_service: Optional[WakeWordService] = None


def initialize_wake_word_service(
    wake_words: list[str] = None,
    threshold: float = 0.5,
    enabled: bool = True
) -> Optional[WakeWordService]:
    """
    Initialize the global wake word service.
    
    Args:
        wake_words: List of wake word models to load
        threshold: Detection threshold
        enabled: Whether to enable wake word detection
        
    Returns:
        WakeWordService instance or None if disabled
    """
    global wake_word_service
    
    if not enabled:
        logger.info("[WakeWord] Wake word detection disabled")
        return None
    
    if not _HAS_OPENWAKEWORD:
        logger.warning("[WakeWord] openwakeword not available, skipping initialization")
        return None
    
    try:
        wake_word_service = WakeWordService(
            wake_words=wake_words,
            threshold=threshold
        )
        logger.info("[WakeWord] Service initialized successfully")
        return wake_word_service
    except Exception as e:
        logger.error(f"[WakeWord] Failed to initialize service: {e}")
        return None


def get_wake_word_service() -> Optional[WakeWordService]:
    """Get the global wake word service instance."""
    return wake_word_service
