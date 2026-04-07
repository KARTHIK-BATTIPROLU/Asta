import logging
from typing import Optional

import httpx

from backend.app.config import config

logger = logging.getLogger(__name__)


class DeepgramSTTError(Exception):
    pass


async def transcribe_audio(file_bytes: bytes, mimetype: str = "audio/webm") -> str:
    if not file_bytes:
        raise DeepgramSTTError("No audio bytes provided")

    if len(file_bytes) > config.MAX_AUDIO_BYTES:
        raise DeepgramSTTError("Audio payload too large")

    if not config.DEEPGRAM_API_KEY:
        raise DeepgramSTTError("DEEPGRAM_API_KEY is missing")

    logger.info("STT started")

    endpoint = "https://api.deepgram.com/v1/listen"
    params = {
        "model": "nova-2",
        "smart_format": "true",
        "punctuate": "true",
    }
    headers = {
        "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
        "Content-Type": mimetype or "audio/webm",
    }

    timeout = httpx.Timeout(config.STT_TIMEOUT_SECONDS)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, params=params, headers=headers, content=file_bytes)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise DeepgramSTTError("Deepgram STT timed out") from exc
    except httpx.HTTPError as exc:
        raise DeepgramSTTError(f"Deepgram STT request failed: {exc}") from exc
    except Exception as exc:
        raise DeepgramSTTError(f"Deepgram STT unexpected error: {exc}") from exc

    transcript: Optional[str] = (
        data.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
    )

    transcript = (transcript or "").strip()
    logger.info("STT completed")
    return transcript
