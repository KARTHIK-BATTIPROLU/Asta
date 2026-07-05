"""
ASTA Notion Service
Handles all reads/writes to Notion databases.
"""
import logging
from datetime import datetime
from typing import Optional
from notion_client import AsyncClient

from backend.app.config import settings

logger = logging.getLogger(__name__)


class NotionService:
    """Service for interacting with Notion databases."""
    
    def __init__(self):
        """Initialize Notion client."""
        self.client = AsyncClient(auth=settings.NOTION_API_KEY)
    
    # ── Research ──────────────────────────────────────────────────────────
    
    async def create_research_page(
        self, 
        topic: str, 
        conversation_summary: str,
        research_points: list, 
        combined_solution: str
    ) -> str:
        """Creates subpage in NOTION_RESEARCH_DB. Returns page_id."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            title = f"Research: {topic} — {today}"
            
            properties = {
                "Project Name": {"title": [{"text": {"content": title}}]},
                "Created Date": {"date": {"start": today}},
                "Status": {"select": {"name": "Completed"}},
            }
            
            blocks = [
                _h2("Conversation Summary"),
                _paragraph(conversation_summary),
                _h2("Research Points"),
                *[_bullet(p) for p in research_points],
                _h2("Combined Solution"),
                _paragraph(combined_solution),
            ]
            
            page = await self.client.pages.create(
                parent={"database_id": settings.NOTION_RESEARCH_DB},
                properties=properties,
                children=blocks
            )
            return page["id"]
        except Exception as e:
            logger.error(f"Failed to create research page: {e}")
            raise

    # ── Routine ───────────────────────────────────────────────────────────

    async def create_routine_task(
        self, 
        task_name: str, 
        task_type: str,
        scheduled_time: str, 
        date: str
    ) -> str:
        """Create a routine task in Notion. Returns page_id."""
        try:
            properties = {
                "Task Name": {"title": [{"text": {"content": task_name}}]},
                "Type": {"select": {"name": task_type}},
                "Scheduled Time": {"rich_text": [{"text": {"content": scheduled_time}}]},
                "Status": {"select": {"name": "Pending"}},
                "Date": {"date": {"start": date}},
            }
            page = await self.client.pages.create(
                parent={"database_id": settings.NOTION_ROUTINE_DB},
                properties=properties
            )
            return page["id"]
        except Exception as e:
            logger.error(f"Failed to create routine task: {e}")
            raise

    async def create_task(
        self,
        task: str,
        time: str = "",
        priority: str = "",
        task_type: str = "Dynamic",
        task_date: str = None,
    ) -> str:
        """
        Convenience wrapper for capturing a routine task.
        Priority is recorded in the task title (the Routine DB schema only has
        Task Name / Type / Scheduled Time / Status / Date), so we keep the
        Notion write to known properties to avoid schema errors.
        """
        task_date = task_date or datetime.now().strftime("%Y-%m-%d")
        title = f"[{priority.upper()}] {task}" if priority else task
        return await self.create_routine_task(
            task_name=title,
            task_type=task_type,
            scheduled_time=time or "",
            date=task_date,
        )

    async def get_pending_tasks(self, date: str) -> list:
        """Get all pending tasks for a specific date."""
        try:
            # Use httpx directly since notion-client v3.0.0 has different API
            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f"https://api.notion.com/v1/databases/{settings.NOTION_ROUTINE_DB}/query",
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "filter": {
                            "and": [
                                {"property": "Date", "date": {"equals": date}},
                                {"property": "Status", "select": {"does_not_equal": "Completed"}}
                            ]
                        }
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query tasks: {response.status_code} - {response.text}")
                    return []
                
                results = response.json()
                tasks = []
                for page in results.get("results", []):
                    props = page["properties"]
                    tasks.append({
                        "page_id": page["id"],
                        "task_name": _get_title(props, "Task Name"),
                        "type": _get_select(props, "Type"),
                        "scheduled_time": _get_text(props, "Scheduled Time"),
                        "status": _get_select(props, "Status"),
                    })
                return tasks
        except Exception as e:
            logger.error(f"Failed to get pending tasks: {e}")
            return []

    async def update_task_status(self, page_id: str, status: str) -> bool:
        """Update task status and track habit streaks."""
        try:
            # Check if this is a habit being marked done
            if status.lower() == "done":
                page = await self.client.pages.retrieve(page_id=page_id)
                task_name = _get_title(page["properties"], "Task")
                task_type = _get_select(page["properties"], "Type")
                
                if task_type.lower() == "habit":
                    # Update Neo4j habit streak
                    from backend.app.core.registry import registry
                    db = registry.get("db")
                    if db and hasattr(db, "neo4j_driver"):
                        try:
                            async with db.neo4j_driver.session() as session:
                                await session.run(
                                    """
                                    MERGE (h:Habit {name: $name})
                                    ON CREATE SET h.current_streak = 1, h.last_completed = date()
                                    ON MATCH SET h.current_streak = CASE 
                                        WHEN h.last_completed = date() - duration('P1D') THEN h.current_streak + 1
                                        WHEN h.last_completed = date() THEN h.current_streak
                                        ELSE 1 END,
                                        h.last_completed = date()
                                    WITH h
                                    MATCH (u:Identity {name: 'KARTHIK'})
                                    MERGE (u)-[:HABIT_STREAK]->(h)
                                    """,
                                    name=task_name
                                )
                                logger.info(f"[Habits] Logged completion for habit: {task_name}")
                        except Exception as ne:
                            logger.error(f"[Habits] Failed to update Neo4j streak: {ne}")

            await self.client.pages.update(
                page_id=page_id,
                properties={"Status": {"select": {"name": status}}}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            return False

    async def update_task_schedule(
        self, page_id: str, scheduled_time: str = None, date: str = None
    ) -> bool:
        """Reschedule a task: update Scheduled Time (rich_text) and/or Date (date)."""
        try:
            properties = {}
            if scheduled_time is not None:
                properties["Scheduled Time"] = {
                    "rich_text": [{"text": {"content": scheduled_time}}]
                }
            if date is not None:
                properties["Date"] = {"date": {"start": date}}
            if not properties:
                return False
            await self.client.pages.update(page_id=page_id, properties=properties)
            return True
        except Exception as e:
            logger.error(f"Failed to update task schedule: {e}")
            return False

    async def delete_completed_tasks(self, date: str) -> int:
        """Archive completed tasks for a specific date. Returns count."""
        try:
            tasks = await self.get_pending_tasks(date)
            count = 0
            for t in tasks:
                if t["status"] == "Completed":
                    await self.client.pages.update(page_id=t["page_id"], archived=True)
                    count += 1
            return count
        except Exception as e:
            logger.error(f"Failed to delete completed tasks: {e}")
            return 0

    async def append_to_gratitude_page(self, entry: str, date: str) -> bool:
        """Append entry to Gratitude Journal page."""
        try:
            # Find the Gratitude Journal page — search by title in NOTION_ROUTINE_DB
            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f"https://api.notion.com/v1/databases/{settings.NOTION_ROUTINE_DB}/query",
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "filter": {"property": "Task Name", "title": {"equals": "Gratitude Journal"}}
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query Gratitude Journal: {response.status_code}")
                    return False
                
                results = response.json()
                
                if not results.get("results"):
                    # Create it if it doesn't exist
                    page = await self.client.pages.create(
                        parent={"database_id": settings.NOTION_ROUTINE_DB},
                        properties={
                            "Task Name": {"title": [{"text": {"content": "Gratitude Journal"}}]},
                            "Status": {"select": {"name": "Permanent"}}
                        }
                    )
                    page_id = page["id"]
                else:
                    page_id = results["results"][0]["id"]
            
            await self.client.blocks.children.append(
                block_id=page_id,
                children=[_paragraph(f"[{date}] {entry}")]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to append to gratitude page: {e}")
            return False

    async def append_to_permanent_memory(self, content: str, tags: list) -> bool:
        """Append content to Permanent Memory page."""
        try:
            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f"https://api.notion.com/v1/databases/{settings.NOTION_ROUTINE_DB}/query",
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "filter": {"property": "Task Name", "title": {"equals": "Permanent Memory"}}
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query Permanent Memory: {response.status_code}")
                    return False
                
                results = response.json()
                
                if not results.get("results"):
                    page = await self.client.pages.create(
                        parent={"database_id": settings.NOTION_ROUTINE_DB},
                        properties={
                            "Task Name": {"title": [{"text": {"content": "Permanent Memory"}}]},
                            "Status": {"select": {"name": "Permanent"}}
                        }
                    )
                    page_id = page["id"]
                else:
                    page_id = results["results"][0]["id"]
            
            tag_str = f"[{', '.join(tags)}]" if tags else ""
            date = datetime.now().strftime("%Y-%m-%d %H:%M")
            await self.client.blocks.children.append(
                block_id=page_id,
                children=[_paragraph(f"[{date}] {tag_str} {content}")]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to append to permanent memory: {e}")
            return False

    # ── Content ───────────────────────────────────────────────────────────

    async def create_linkedin_page(
        self,
        topic: str,
        post_body: str,
        hashtags: list,
        discussion_summary: str,
        images: list = None,
    ) -> str:
        """Create LinkedIn content page. Returns page_id."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            properties = {
                "Name": {"title": [{"text": {"content": f"LinkedIn: {topic} — {today}"}}]},
                "Date": {"date": {"start": today}},
                "Status": {"select": {"name": "Draft"}},
                "Workflow": {"select": {"name": "LinkedIn"}},
            }
            blocks = [
                _h2("Discussion Summary"),
                _paragraph(discussion_summary),
                _h2("Post Body"),
                _paragraph(post_body),
                _h2("Hashtags"),
                _paragraph(" ".join(hashtags)),
                *_images_section(images),
            ]
            page = await self.client.pages.create(
                parent={"database_id": settings.NOTION_CONTENT_DB},
                properties=properties, 
                children=blocks
            )
            return page["id"]
        except Exception as e:
            logger.error(f"Failed to create LinkedIn page: {e}")
            raise

    async def create_youtube_page(
        self,
        topic: str,
        script: str,
        research_points: list,
        metadata: dict,
        images: list = None,
    ) -> str:
        """Create YouTube content page. Returns page_id."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            properties = {
                "Name": {"title": [{"text": {"content": f"YouTube: {topic} — {today}"}}]},
                "Date": {"date": {"start": today}},
                "Status": {"select": {"name": "Script Ready"}},
                "Workflow": {"select": {"name": "YouTube"}},
            }
            blocks = [
                _h2("Research Points"),
                *[_bullet(p) for p in research_points],
                _h2("Full Script"),
                _paragraph(script),
                _h2("Video Metadata"),
                _paragraph(f"Title ideas: {', '.join(metadata.get('title_ideas',[]))}"),
                _paragraph(f"Tags: {', '.join(metadata.get('tags',[]))}"),
                *_images_section(images),
            ]
            page = await self.client.pages.create(
                parent={"database_id": settings.NOTION_YOUTUBE_DB},
                properties=properties, 
                children=blocks
            )
            return page["id"]
        except Exception as e:
            logger.error(f"Failed to create YouTube page: {e}")
            raise

    async def create_instagram_page(
        self,
        topic: str,
        caption: str,
        hashtags: list,
        slides: list,
        images: list = None,
    ) -> str:
        """Create Instagram content page. Returns page_id."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            properties = {
                "Name": {"title": [{"text": {"content": f"Instagram: {topic} — {today}"}}]},
                "Date": {"date": {"start": today}},
                "Status": {"select": {"name": "Draft"}},
                "Workflow": {"select": {"name": "Instagram"}},
            }
            slide_blocks = []
            for i, slide in enumerate(slides):
                slide_blocks.append(_h2(f"Slide {i+1}"))
                slide_blocks.append(_paragraph(slide))
            blocks = [
                _h2("Caption"),
                _paragraph(caption),
                _h2("Hashtags"),
                _paragraph(" ".join(hashtags)),
                *slide_blocks,
                *_images_section(images),
            ]
            page = await self.client.pages.create(
                parent={"database_id": settings.NOTION_CONTENT_DB},
                properties=properties, 
                children=blocks
            )
            return page["id"]
        except Exception as e:
            logger.error(f"Failed to create Instagram page: {e}")
            raise

    async def log_content_creation(self, platform: str, topic: str, summary: str) -> bool:
        """Log content creation activity."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            await self.client.pages.create(
                parent={"database_id": settings.NOTION_CONTENT_DB},
                properties={
                    "Name": {"title": [{"text": {"content": f"[LOG] {platform}: {topic}"}}]},
                    "Date": {"date": {"start": today}},
                    "Status": {"select": {"name": "Logged"}},
                },
                children=[_paragraph(summary)]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log content creation: {e}")
            return False

    async def delete_page(self, page_id: str) -> bool:
        """Archive a Notion page."""
        try:
            await self.client.pages.update(page_id=page_id, archived=True)
            return True
        except Exception as e:
            logger.error(f"Failed to delete page: {e}")
            return False

    # ── Habit Tracking ────────────────────────────────────────────────────

    async def append_to_habit_page(self, habit_type: str, content: str) -> bool:
        """Append content to a habit tracking page."""
        try:
            # Find or create the habit page by habit_type title
            title_map = {
                "dsa": "DSA Progress Tracker",
                "reading": "Books Bucket List",
                "gratitude": "Gratitude Journal",
                "metaverse": "Metaverse Knowledge Base",
                "community": "Community Goals",
                "goals": "Professional Goals",
            }
            page_title = title_map.get(habit_type, f"Habit: {habit_type}")
            
            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f"https://api.notion.com/v1/databases/{settings.NOTION_ROUTINE_DB}/query",
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "filter": {"property": "Task Name", "title": {"equals": page_title}}
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query habit page: {response.status_code}")
                    return False
                
                results = response.json()
                
                if results.get("results"):
                    page_id = results["results"][0]["id"]
                else:
                    page = await self.client.pages.create(
                        parent={"database_id": settings.NOTION_ROUTINE_DB},
                        properties={
                            "Task Name": {"title": [{"text": {"content": page_title}}]},
                            "Status": {"select": {"name": "Permanent"}}
                        }
                    )
                    page_id = page["id"]
            
            date = datetime.now().strftime("%Y-%m-%d %H:%M")
            await self.client.blocks.children.append(
                block_id=page_id,
                children=[_paragraph(f"[{date}] {content}")]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to append to habit page: {e}")
            return False


# ── Block Helpers (module-level) ─────────────────────────────────────────────

def _h2(text: str) -> dict:
    """Create a heading 2 block."""
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }


def _paragraph(text: str) -> dict:
    """Create a paragraph block."""
    safe = text[:2000] if text else ""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": safe}}]
        }
    }


def _images_section(images: list) -> list:
    """Build an 'Images' block section from image_service.generate_images() output.

    Real Imagen output is base64 (can't be embedded as a Notion image block
    without external hosting), so we log the prompt either way — Kartik can
    regenerate via DALL-E/Midjourney from the prompt if Imagen wasn't available.
    """
    if not images:
        return []
    blocks = [_h2("Images")]
    for i, img in enumerate(images, 1):
        if img.get("type") == "base64":
            blocks.append(_paragraph(f"Image {i}: generated via Imagen. Prompt: {img.get('prompt','')[:400]}"))
        else:
            blocks.append(_paragraph(f"Image {i} prompt (use with DALL-E/Midjourney): {img.get('prompt','')[:500]}"))
    return blocks


def _bullet(text: str) -> dict:
    """Create a bulleted list item block."""
    safe = text[:2000] if text else ""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": safe}}]
        }
    }


def _get_title(props: dict, key: str) -> str:
    """Extract title property from Notion page properties."""
    try:
        return props[key]["title"][0]["text"]["content"]
    except:
        return ""


def _get_select(props: dict, key: str) -> str:
    """Extract select property from Notion page properties."""
    try:
        return props[key]["select"]["name"]
    except:
        return ""


def _get_text(props: dict, key: str) -> str:
    """Extract rich text property from Notion page properties."""
    try:
        return props[key]["rich_text"][0]["text"]["content"]
    except:
        return ""


# Global instance
notion_service = NotionService()
