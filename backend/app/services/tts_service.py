import httpx
import logging
from backend.app.config import config as settings
from typing import AsyncGenerator

logger = logging.getLogger("TTS_Service")

class DeepgramTTSError(Exception):
    pass

async def synthesize_speech_stream(text: str) -> AsyncGenerator[bytes, None]:
    """Stream TTS PCM chunks directly from Deepgram (used for WebSockets)."""
    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    params = {
        "model": "aura-angus-en",
        "encoding": "linear16",
        "sample_rate": 24000
    }
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        async with client.stream(
            "POST",
            "https://api.deepgram.com/v1/speak",
            headers=headers,
            params=params,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=4096):
                yield chunk

async def text_to_speech(text: str) -> bytes:
    """Return a fully buffered TTS MP3 payload (used for REST / Notifications)."""
    if not text or not text.strip():
        raise DeepgramTTSError("No text provided for TTS")

    if not settings.DEEPGRAM_API_KEY:
        raise DeepgramTTSError("DEEPGRAM_API_KEY is missing")

    endpoint = "https://api.deepgram.com/v1/speak"
    params = {"model": "aura-angus-en", "encoding": "mp3"}
    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    timeout = httpx.Timeout(settings.TTS_TIMEOUT_SECONDS if hasattr(settings, 'TTS_TIMEOUT_SECONDS') else 15.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, params=params, headers=headers, json={"text": text})
            response.raise_for_status()
            audio = response.content
    except httpx.TimeoutException as exc:
        raise DeepgramTTSError("Deepgram TTS timed out") from exc
    except httpx.HTTPError as exc:
        raise DeepgramTTSError(f"Deepgram TTS request failed: {exc}") from exc
    except Exception as exc:
        raise DeepgramTTSError(f"Deepgram TTS unexpected error: {exc}") from exc

    logger.info("TTS generated")
    return audio
