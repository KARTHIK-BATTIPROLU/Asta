import logging

import httpx

from backend.app.config import config

logger = logging.getLogger(__name__)


class DeepgramTTSError(Exception):
    pass


async def text_to_speech(text: str) -> bytes:
    if not text or not text.strip():
        raise DeepgramTTSError("No text provided for TTS")

    if not config.DEEPGRAM_API_KEY:
        raise DeepgramTTSError("DEEPGRAM_API_KEY is missing")

    endpoint = "https://api.deepgram.com/v1/speak"
    params = {"model": "aura-asteria-en", "encoding": "mp3"}
    headers = {
        "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    timeout = httpx.Timeout(config.TTS_TIMEOUT_SECONDS)

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
