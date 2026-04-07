import logging
import collections
import struct
try:
    import webrtcvad
    _HAS_WEBRTCVAD = True
except ModuleNotFoundError:
    webrtcvad = None
    _HAS_WEBRTCVAD = False

logger = logging.getLogger(__name__)

class VADService:
    def __init__(self, mode: int = 2, frame_duration_ms: int = 20, sample_rate: int = 16000):
        """
        Initializes the Voice Activity Detection (VAD) Service.
        
        Args:
            mode (int): The aggressiveness mode of the VAD (0 to 3). 0 is least aggressive.
            frame_duration_ms (int): Duration of a frame in milliseconds (10, 20, or 30).
            sample_rate (int): Sampling rate in Hz (8000, 16000, 32000, 48000).
        """
        self.vad = webrtcvad.Vad(mode) if _HAS_WEBRTCVAD else None
        if not _HAS_WEBRTCVAD:
            logger.warning("webrtcvad not installed; falling back to pass-through VAD mode")
        self.frame_duration_ms = frame_duration_ms
        self.sample_rate = sample_rate
        # Bytes per frame: (Sample Rate * Frame Duration / 1000) * 2 bytes/sample (16-bit PCM)
        self.frame_size = int(sample_rate * frame_duration_ms / 1000) * 2
        self.buffer = bytearray()
        self.speech_chunks = []
        self.is_speech_active = False
        
        # Performance metric
        self.vad_calls = 0
        self.vad_speech_count = 0

    def is_speech(self, frame_bytes: bytes) -> bool:
        """
        Determines if a frame of audio contains speech.
        
        Args:
            frame_bytes (bytes): Raw PCM audio data for a single frame.
            
        Returns:
            bool: True if speech is detected, False otherwise.
        """
        try:
            if self.vad is None:
                return True

            if len(frame_bytes) != self.frame_size:
                # Incomplete frame (edge case or end of stream)
                # logger.debug(f"VAD: Frame size mismatch {len(frame_bytes)} != {self.frame_size}")
                return False
                
            return self.vad.is_speech(frame_bytes, self.sample_rate)
        except Exception as e:
            # Fallback for non-PCM or invalid format (keeps stream alive)
            # logger.warning(f"VAD Error (likely format mismatch): {e}")
            return True 

    def process_audio_stream(self, audio_chunk: bytes) -> bytes:
        """
        Processes an incoming audio chunk, extracting only speech frames.
        Buffers partial frames to ensure correct frame size for VAD.
        
        Args:
            audio_chunk (bytes): Incoming raw audio data.
            
        Returns:
            bytes: Valid speech audio data (or empty if silence).
        """
        self.buffer.extend(audio_chunk)
        speech_out = bytearray()
        
        while len(self.buffer) >= self.frame_size:
            frame = self.buffer[:self.frame_size]
            del self.buffer[:self.frame_size]
            
            if self.is_speech(bytes(frame)):
                speech_out.extend(frame)
                if not self.is_speech_active:
                    self.is_speech_active = True
                    logger.info("Speech started")
                    self.vad_speech_count += 1
            else:
                # Silence logic - could implement a hangover/smoothing here
                if self.is_speech_active:
                     # Simple logic: silence breaks speech block
                     # For very sophisticated VAD, we'd use a ring buffer
                     self.is_speech_active = False
                     logger.info("Speech ended (Silence)")
                # Drop silence frame
                pass
                
        return bytes(speech_out)

    def reset(self):
        """Resets the VAD state and buffer."""
        self.buffer = bytearray()
        self.is_speech_active = False
