import httpx
from backend.app.config import config as settings

from typing import AsyncGenerator

async def synthesize_speech_stream(text: str) -> AsyncGenerator[bytes, None]:
    """Stream TTS PCM chunks directly from Deepgram."""
    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    params = {
        "model": "aura-asteria-en",
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
