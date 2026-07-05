import logging

from backend.app.services.stt_service import transcribe_audio
from backend.app.services.tts_service import text_to_speech

logger = logging.getLogger(__name__)


class DeepgramService:
    async def transcribe(self, audio_data: bytes, mimetype: str = "audio/webm") -> str:
        return await transcribe_audio(audio_data, mimetype=mimetype)

    async def speak(self, text: str) -> bytes:
        return await text_to_speech(text)


deepgram_service = DeepgramService()
