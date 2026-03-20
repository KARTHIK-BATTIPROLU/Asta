import os
import logging
from deepgram import DeepgramClient

logger = logging.getLogger(__name__)

class DeepgramTTS:
    def __init__(self):
        try:
            api_key = os.getenv("DEEPGRAM_API_KEY")
            if not api_key:
                logger.error("DEEPGRAM_API_KEY not found.")
                self.client = None
            else:
                self.client = DeepgramClient(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Deepgram TTS client: {e}")
            self.client = None

    def synthesize(self, text: str) -> bytes:
        if not self.client:
            logger.error("TTS client not initialized.")
            return b""

        try:
            # Aura model options
            options = {"model": "aura-asteria-en"} 
            
            response = self.client.speak.v("1").stream({"text": text}, options)
            
            # Helper to get bytes from stream
            buffer = response.stream
            if hasattr(buffer, "read"):
                return buffer.read()
            elif hasattr(buffer, "getvalue"):
                return buffer.getvalue()
            else:
                 return bytes(buffer)

        except Exception as e:
            logger.error(f"TTS error: {e}")
            return b""

deepgram_tts = DeepgramTTS()
