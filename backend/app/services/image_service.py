"""
ASTA Image Generation Service
Uses Google Gemini for image generation via Imagen API.
"""
import logging
import asyncio
import base64

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logging.warning("google-generativeai not installed. Image generation will be limited.")

from backend.app.config import settings

logger = logging.getLogger(__name__)


class ImageService:
    """Service for generating images for content."""
    
    def __init__(self):
        """Initialize image service."""
        if GENAI_AVAILABLE and settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
    
    async def generate_images(self, topic: str, post_body: str, count: int = 4) -> list:
        """Generate images for a topic and post. Returns list of image data."""
        prompt = await self._build_image_prompt(topic, post_body)
        images = []
        
        try:
            if not GENAI_AVAILABLE:
                raise Exception("google-generativeai not installed")
            
            model = genai.ImageGenerationModel("imagen-3.0-generate-001")
            result = await asyncio.to_thread(
                model.generate_images,
                prompt=prompt,
                number_of_images=min(count, 4),
                aspect_ratio="1:1"
            )
            for img in result.images:
                b64 = base64.b64encode(img._image_bytes).decode()
                images.append({
                    "type": "base64",
                    "data": b64,
                    "prompt": prompt
                })
            logger.info(f"Generated {len(images)} images for topic: {topic}")
        except Exception as e:
            logger.warning(
                f"Imagen generation failed: {e}. Returning prompt descriptions."
            )
            for i in range(count):
                images.append({
                    "type": "prompt_only",
                    "data": None,
                    "prompt": f"{prompt} (variation {i+1})",
                    "note": "Image generation unavailable — use prompt with DALL-E or Midjourney"
                })
        
        return images
    
    async def _build_image_prompt(self, topic: str, post_body: str) -> str:
        """Build an image generation prompt using LLM."""
        from app.core.llm_router import llm_router
        
        try:
            return await llm_router.invoke_with_system(
                "image_prompt",
                "Generate a professional LinkedIn image prompt. Clean, modern, "
                "tech-focused. No text in image. Max 50 words.",
                f"Topic: {topic}\nPost: {post_body[:300]}"
            )
        except Exception as e:
            logger.error(f"Failed to build image prompt: {e}")
            return f"Professional illustration about {topic}, modern tech style, clean design"


# Global instance
image_service = ImageService()
