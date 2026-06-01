"""
ImageTool â€” Image generation via Google Gemini (Imagen).

Operations: generate, generate_with_text
Provider: Gemini API (GEMINI_API_KEY env var)
Output: /tmp/asta_images/ + base64
"""

import asyncio
import base64
import logging
import os
import time
from pathlib import Path

import httpx

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("ImageTool")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TIMEOUT = 30.0  # Image gen takes longer
MAX_RETRIES = 2
OUTPUT_DIR = Path("/tmp/asta_images")

STYLE_PREFIXES = {
    "professional": "Professional LinkedIn post image, high quality, clean corporate tech aesthetic, ",
    "creative": "Professional LinkedIn post image, vibrant eye-catching creative design, ",
    "minimal": "Professional LinkedIn post image, minimal white background simple graphic, ",
}


class ImageTool(BaseTool):
    name = "image"
    description = "Generate professional images for LinkedIn posts and content via Google Gemini Imagen."

    async def validate(self, payload: dict) -> tuple[bool, str]:
        operation = payload.get("operation", "")
        if operation not in ("generate", "generate_with_text"):
            return False, f"Invalid operation '{operation}'. Must be: generate, generate_with_text"

        if not payload.get("prompt"):
            return False, "Missing 'prompt' field"

        if not GEMINI_API_KEY:
            return False, "GEMINI_API_KEY not configured in environment"

        return True, ""

    async def execute(self, payload: dict) -> dict:
        operation = payload["operation"]
        prompt = payload["prompt"]
        style = payload.get("style", "professional")
        size = payload.get("size", "1024x1024")

        # Build enriched prompt
        prefix = STYLE_PREFIXES.get(style, STYLE_PREFIXES["professional"])
        full_prompt = f"{prefix}{prompt}"

        if operation == "generate_with_text":
            overlay = payload.get("overlay_text", "")
            if overlay:
                full_prompt += f". Include the text '{overlay}' in the image."

        return await self._generate_image(full_prompt, size)

    async def _generate_image(self, prompt: str, size: str) -> dict:
        """Generate image via Gemini Imagen API."""
        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Parse dimensions
        try:
            width, height = map(int, size.split("x"))
        except ValueError:
            width, height = 1024, 1024

        # Gemini Imagen endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict"
        headers = {"Content-Type": "application/json"}
        params = {"key": GEMINI_API_KEY}

        body = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "1:1" if width == height else "16:9",
            },
        }

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(url, json=body, headers=headers, params=params)

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(f"[Image] Rate limited. Retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code >= 400:
                        error_text = resp.text[:300]
                        logger.error(f"[Image] API error {resp.status_code}: {error_text}")
                        return {"error": f"Imagen API {resp.status_code}: {error_text}"}

                    data = resp.json()
                    predictions = data.get("predictions", [])
                    if not predictions:
                        return {"error": "No image generated â€” empty predictions"}

                    # Extract base64 image
                    b64_image = predictions[0].get("bytesBase64Encoded", "")
                    if not b64_image:
                        return {"error": "No image data in response"}

                    # Save to disk
                    timestamp = int(time.time())
                    filename = f"asta_{timestamp}.png"
                    filepath = OUTPUT_DIR / filename

                    image_bytes = base64.b64decode(b64_image)
                    filepath.write_bytes(image_bytes)

                    logger.info(f"[Image] Generated: {filepath} ({len(image_bytes)} bytes)")

                    return {
                        "data": {
                            "file_path": str(filepath),
                            "filename": filename,
                            "size_bytes": len(image_bytes),
                            "dimensions": f"{width}x{height}",
                            "base64": b64_image[:100] + "..." if len(b64_image) > 100 else b64_image,
                            "base64_full": b64_image,
                        },
                        "message": f"Image generated: {filepath}",
                    }

            except httpx.TimeoutException:
                if attempt == MAX_RETRIES - 1:
                    return {"error": "Image generation timed out (30s)"}
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"Image generation failed: {e}"}
                await asyncio.sleep(2 ** attempt)

        return {"error": "Image generation failed after retries"}
