import httpx
import logging
import asyncio
from backend.app.config import config as settings
from typing import Optional

logger = logging.getLogger("STT_Service")

class DeepgramSTTError(Exception):
    pass

async def transcribe_audio(audio_bytes: bytes, mimetype: str = "application/octet-stream", retries: int = 2) -> str:
    """Send raw audio to Deepgram, get back transcript text. Retries on transient errors."""
    
    if not audio_bytes or len(audio_bytes) < 100:
        logger.warning(f"[STT] Audio too small ({len(audio_bytes)} bytes), skipping")
        return ""
        
    if len(audio_bytes) > settings.MAX_AUDIO_BYTES:
        raise DeepgramSTTError("Audio payload too large")
        
    if not settings.DEEPGRAM_API_KEY:
        raise DeepgramSTTError("DEEPGRAM_API_KEY is missing")
    
    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": mimetype,
    }
    
    params = {
        "model": "nova-2",
        "language": "en-US",
        "smart_format": "true",
        "punctuate": "true",
    }
    
    # If the transport is streaming raw PCM from Websockets, tell Deepgram
    if mimetype == "application/octet-stream":
        params.update({
            "encoding": "linear16",
            "sample_rate": "24000",
        })
    
    last_error = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    headers=headers,
                    params=params,
                    content=audio_bytes,
                )
                response.raise_for_status()
                result = response.json()
            
            # Extract transcript from response
            transcript = (
                result.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
            )
            return (transcript or "").strip()
            
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.warning(f"[STT] Attempt {attempt+1}/{retries} failed: {e.response.status_code}")
            if e.response.status_code == 400 and attempt < retries - 1:
                await asyncio.sleep(0.5)
                continue
            break
        except Exception as e:
            last_error = e
            logger.error(f"[STT] Attempt {attempt+1}/{retries} error: {type(e).__name__}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(0.5)
                continue
            break
    
    logger.error(f"[STT] All {retries} attempts failed: {last_error}")
    raise DeepgramSTTError(f"STT failed after {retries} attempts: {last_error}")

