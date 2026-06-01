import logging
import asyncio
import os
from pathlib import Path
from groq import AsyncGroq
from backend.app.config import config as settings
from backend.app.models.action_model import ActionRequest
from backend.app.core.registry import registry

logger = logging.getLogger("YouTubeEngine")

class YouTubeEngine:
    """
    ASTA YouTube Engine (Groq Only)
    Executes deep research loops for video topics and generates YouTube scripts
    configured for Karthik's specific channel preferences.
    """
    def __init__(self):
        self.groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model_name = "llama-3.3-70b-versatile"
        
        # Determine the database to use (fallback to content DB if youtube DB isn't strictly defined)
        self.youtube_db_id = getattr(settings, "NOTION_YOUTUBE_DB", "").strip()
        if not self.youtube_db_id:
            self.youtube_db_id = getattr(settings, "NOTION_CONTENT_DB", "").strip()

    async def _get_executor(self):
        executor = registry.get("action_executor")
        if not executor:
            logger.warning("[YouTubeEngine] ActionExecutor not found in registry.")
        return executor

    async def _read_preferences(self) -> str:
        """
        Reads YouTube tone/style preferences from local storage.
        """
        pref_file = Path("preferences/youtube.md")
        if pref_file.exists():
            try:
                with open(pref_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"[YouTubeEngine] Error reading preference file {pref_file}: {e}")
        
        return (
            "Write an engaging YouTube script. Start with a cold open hook to retain viewers. "
            "Keep the pacing fast. Use an enthusiastic, expert, yet conversational tone. "
            "Include clear visual cues or b-roll suggestions in brackets."
        )

    async def generate_script(self, topic: str, session_id: str) -> str:
        """
        Workflow:
        1. Deep research via SearchTool.
        2. Aggregate data and YouTube preferences.
        3. Draft full YouTube video script.
        4. Save to Notion DB.
        """
        executor = await self._get_executor()
        if not executor:
            return "Error: YouTube subsystems offline."

        logger.info(f"Generating YouTube Script for '{topic}' [Session: {session_id}]")

        # Step 1: Read Preferences
        preferences = await self._read_preferences()

        # Step 2: Deep Research
        search_req = ActionRequest(
            session_id=session_id,
            tool_name="search",
            parameters={"operation": "deep_search", "query": f"latest trends details {topic}", "num_results": 5},
            intent=f"Researching deep facts for YouTube video on {topic}",
            memory_tag=f"youtube:{topic.lower().replace(' ', '_')}"
        )
        search_res = await executor.execute_action(search_req)
        
        raw_research = search_res.result if search_res.status == "success" else f"Search Failed: {search_res.result}"

        # Step 3: Draft Script
        draft = await self._draft_script(topic, raw_research, preferences)

        # Step 4: Save to Notion
        notion_status = "Skipped"
        if self.youtube_db_id:
            page_content = f"### Research Data\n{raw_research}\n\n### Video Script\n{draft}"
            notion_req = ActionRequest(
                session_id=session_id,
                tool_name="notion",
                parameters={
                    "operation": "create_page",
                    "database": "youtube" if hasattr(settings, "NOTION_YOUTUBE_DB") and settings.NOTION_YOUTUBE_DB else "content", 
                    "title": f"[YOUTUBE] {topic.title()}",
                    "content": page_content
                },
                intent=f"Saving YouTube script for {topic}",
                memory_tag=f"youtube:{topic.lower().replace(' ', '_')}"
            )
            n_res = await executor.execute_action(notion_req)
            notion_status = n_res.status
            if notion_status != "success":
                logger.error(f"[YouTubeEngine] Failed to save draft to Notion: {n_res.result}")
        else:
            logger.warning("[YouTubeEngine] NOTION_YOUTUBE_DB/NOTION_CONTENT_DB not configured. Skipping Notion sync.")

        # Step 5: Audio confirmation
        return await self._generate_spoken_summary(topic, notion_status == "success")

    async def _draft_script(self, topic: str, research: str, preferences: str) -> str:
        """
        Drafts the structural script using Groq.
        """
        system_prompt = f"""You are ASTA, writing a YouTube video script for Karthik.
Topic: {topic}

STYLE & PREFERENCES:
{preferences}

Use this raw research to inform the script content organically:
{research[:3000]} # Truncated to avoid context overflow

Write the video script. Output ONLY the drafted script text. Use visual cue brackets like [B-Roll: ...].
"""
        try:
            stream = await self.groq_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please draft the script for: {topic}"}
                ],
                temperature=0.6,
                max_tokens=2500
            )
            return stream.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[YouTubeEngine] Script drafting error: {e}")
            return f"Failed to draft script: {e}"

    async def _generate_spoken_summary(self, topic: str, saved_notion: bool) -> str:
        """
        Voice summary.
        """
        base = f"I've completed the deep research and drafted a YouTube script for {topic}."
        db_msg = " It's been saved to your Notion database." if saved_notion else " It's sitting in my temporary memory buffer."
        
        try:
            stream = await self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are ASTA updating Karthik. Combine the status into one spoken sentence."},
                    {"role": "user", "content": f"Status: {base}{db_msg}"}
                ],
                temperature=0.4,
                max_tokens=80
            )
            return stream.choices[0].message.content.strip()
        except Exception:
            return base + db_msg

# Singleton instance
youtube_engine = YouTubeEngine()
