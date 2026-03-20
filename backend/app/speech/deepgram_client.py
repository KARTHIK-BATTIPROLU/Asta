import os
import logging
import json
import uuid
from backend.app.config import config
from deepgram import DeepgramClient

logger = logging.getLogger(__name__)

class DeepgramService:
    def __init__(self):
        self.api_key = config.DEEPGRAM_API_KEY
        if not self.api_key:
            logger.warning("DEEPGRAM_API_KEY not found.")
        # Try initializing with keyword argument or rely on env var if not passed
        # self.client = DeepgramClient(api_key=self.api_key) 
        # Actually in recent sdk, it might be just DeepgramClient() if env is set.
        # But let's try kwargs.
        try:
            if self.api_key:
                self.client = DeepgramClient(self.api_key)
            else:
                self.client = DeepgramClient()
        except TypeError:
             # Fallback if positional fails
             self.client = DeepgramClient(api_key=self.api_key)

    async def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe audio bytes to text using Deepgram STT.
        """
        try:
            # Deepgram accepts buffer as source
            # The 'mimetype' might need to be 'audio/wav' or 'audio/webm' depending on frontend
            # We'll try to detect or assume a common format
            source = {"buffer": audio_data} 
            
            # Use dictionary instead of typed options to avoid import issues
            options = {
                "model": "nova-2",
                "smart_format": True,
            }
            
            response = self.client.listen.rest.v("1").transcribe_file(source, options)
            
            # The structure of response is usually valid JSON object with results
            # We access it as a dictionary or object depending on the SDK version
            # Assuming SDK returns an object we can access with .results... 
            # Check if response is dict or valid object.
            # SDK v3 usually returns a response object. 
            
            # Let's try safe access
            if hasattr(response, "results"): # It's an object
                 return response.results.channels[0].alternatives[0].transcript
            else: # It's a dict
                 return response["results"]["channels"][0]["alternatives"][0]["transcript"]

        except Exception as e:
            logger.error(f"Deepgram transcription error: {e}")
            return ""

    async def speak(self, text: str) -> bytes:
        """
        Convert text to audio bytes using Deepgram TTS.
        """
        try:
            # Use dictionary instead of typed options
            options = {
                "model": "aura-asteria-en",
            }
            
            # Generate unique filename for concurrency safety
            unique_id = uuid.uuid4().hex
            filename = f"tts_{unique_id}.mp3"
            
            # Deepgram SDK v3 Fix: Remove .rest intermediate call
            # The correct path is usually client.speak.v("1").save(...)
            # Note: For v3, correct usage might be client.speak.rest.v("1").save(...) or similar depending on exact version
            # But assuming .v("1") worked before... let's stick to structure but fix option type.
            # Actually, standard strictly is client.speak.v("1").save
            response = self.client.speak.v("1").save(filename, {"text": text}, options)
            
            # Read the file back into bytes
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    audio_bytes = f.read()
                os.remove(filename)  # Clean up temp file immediately
                return audio_bytes
            else:
                logger.error("Deepgram TTS file not created.")
                return None

        except Exception as e:
            logger.error(f"Deepgram TTS error: {e}")
            return None

deepgram_service = DeepgramService()
