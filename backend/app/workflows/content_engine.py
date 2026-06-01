import logging
import asyncio
import os
from pathlib import Path
from groq import AsyncGroq
from backend.app.config import config as settings
from backend.app.models.action_model import ActionRequest
from backend.app.core.registry import registry

logger = logging.getLogger("ContentEngine")

class ContentEngine:
    """
    ASTA Content Creation Engine (Groq Only)
    Generates social media content (e.g., LinkedIn posts) by reading local preferences,
    generating an image via Gemini ImageTool, drafting via Llama-3, and saving to Notion.
    """
    def __init__(self):
        self.groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model_name = "llama-3.3-70b-versatile"
        self.content_db_id = getattr(settings, "NOTION_CONTENT_DB", "").strip()

    async def _get_executor(self):
        """Retrieve ActionExecutor lazily from the registry."""
        executor = registry.get("action_executor")
        if not executor:
            logger.warning("[ContentEngine] ActionExecutor not found in registry.")
        return executor

    async def _read_preferences(self, platform: str) -> str:
        """
        Reads tone/style preferences for the specified platform.
        Attempts to read from a local preferences file, defaulting if not found.
        """
        pref_file = Path(f"preferences/{platform.lower()}.md")
        if pref_file.exists():
            try:
                with open(pref_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"[ContentEngine] Error reading preference file {pref_file}: {e}")
        
        # Default prompt if custom preferences file isn't present
        return (f"Write an engaging, professional post tailored for {platform}. "
                "Keep the tone direct, concise, and insightful. Avoid heavy jargon unless necessary, "
                "and ensure a strong but natural hook.")

    async def generate_post(self, topic: str, platform: str, session_id: str) -> str:
        """
        Workflow:
        1. Read preferences for platform.
        2. Prompt Gemini Image API tool.
        3. Draft text content via Groq LLaMA-3.
        4. Save combined Output to Notion (ASTA Content Calendar).
        """
        executor = await self._get_executor()
        if not executor:
            return "Error: Content orchestration subsystems are offline."

        logger.info(f"Generating {platform} content on '{topic}' [Session: {session_id}]")

        # Step 1: Read Style Preferences
        preferences = await self._read_preferences(platform)

        # Step 2: Trigger ImageTool
        image_req = ActionRequest(
            session_id=session_id,
            tool_name="image",
            parameters={
                "operation": "generate", 
                "prompt": f"Professional, stylistic editorial cover image for a tech blog post about: {topic}"
            },
            intent=f"Generate cover image for {platform} post about {topic}",
            memory_tag=f"content:{topic.lower().replace(' ', '_')}"
        )
        image_res = await executor.execute_action(image_req)
        
        if image_res.status == "success":
            image_context = f"Image Generated: {image_res.result}"
        else:
            image_context = f"Image Generation Failed: {image_res.result}"
            logger.warning(f"[ContentEngine] Image generation skipped/failed: {image_res.result}")

        # Step 3: Draft the Content
        draft = await self._draft_content(topic, platform, preferences)

        # Step 4: Save to Notion (ASTA Content Calendar)
        notion_status = "Skipped"
        if self.content_db_id:
            page_content = f"### Asset Status\n{image_context}\n\n### Draft\n{draft}"
            notion_req = ActionRequest(
                session_id=session_id,
                tool_name="notion",
                parameters={
                    "operation": "create_page",
                    "database": "content",
                    "title": f"[{platform.upper()}] {topic.title()}",
                    "content": page_content
                },
                intent=f"Saving {platform} content draft for {topic}",
                memory_tag=f"content:{topic.lower().replace(' ', '_')}"
            )
            n_res = await executor.execute_action(notion_req)
            notion_status = n_res.status
            if notion_status != "success":
                logger.error(f"[ContentEngine] Failed to save draft to Notion: {n_res.result}")
        else:
            logger.warning("[ContentEngine] NOTION_CONTENT_DB not configured. Skipping Notion sync.")

        # Step 5: Spoken Audio Confirmation
        return await self._generate_spoken_summary(topic, platform, image_res.status == "success", notion_status == "success")

    async def _draft_content(self, topic: str, platform: str, preferences: str) -> str:
        """
        Drafts the content using groq llama-3.3-70b
        """
        system_prompt = f"""You are ASTA, drafting content for Karthik.
Platform target: {platform}.
Topic: {topic}

STYLE & PREFERENCES:
{preferences}

Write the actual post content. Output ONLY the drafted post text. Do not include markdown meta-commentary like "Here is your post:".
"""
        try:
            stream = await self.groq_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please draft the {platform} post on: {topic}"}
                ],
                temperature=0.6,
                max_tokens=1024
            )
            return stream.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[ContentEngine] Drafting error via Groq: {e}")
            return f"Draft synthesis failed due to an error: {e}"

    async def _generate_spoken_summary(self, topic: str, platform: str, has_image: bool, saved_notion: bool) -> str:
        """
        Produce a fast vocal summary so the user knows what happened.
        """
        base_status = f"I've drafted a new {platform} post about {topic}."
        img_status = " A cover image was successfully generated." if has_image else " I skipped the image generation."
        notion_status = " The draft and assets have been saved to your Content Calendar in Notion." if saved_notion else " I couldn't save it to Notion, but it's in my memory."
        
        system_prompt = "You are ASTA updating Karthik via voice. Combine the provided status points into one casual, very brief spoken sentence. No lists."
        
        try:
            stream = await self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Combine: {base_status}{img_status}{notion_status}"}
                ],
                temperature=0.4,
                max_tokens=80
            )
            return stream.choices[0].message.content.strip()
        except Exception:
            return base_status + img_status + notion_status

# Singleton instance
content_engine = ContentEngine()
