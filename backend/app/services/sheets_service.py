"""
ASTA Google Sheets Service
Manages LinkedIn content pipeline in Google Sheets.
"""
import logging
import asyncio
import uuid
import gspread
from google.oauth2.service_account import Credentials

from backend.app.config import settings

logger = logging.getLogger(__name__)


class SheetsService:
    """Service for managing Google Sheets content pipeline."""
    
    def __init__(self):
        """Initialize sheets service."""
        self.gc = None
        self.sheet = None
    
    async def connect(self):
        """Connect to Google Sheets using service account."""
        try:
            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file(
                settings.GOOGLE_SA_KEY_PATH,
                scopes=scopes
            )
            self.gc = await asyncio.to_thread(gspread.authorize, creds)
            logger.info("Connected to Google Sheets")
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise
    
    async def _get_sheet(self):
        """Get or create the ASTA LinkedIn Pipeline sheet."""
        if not self.gc:
            await self.connect()
        try:
            sh = await asyncio.to_thread(self.gc.open, "ASTA LinkedIn Pipeline")
            return sh.sheet1
        except:
            # Create sheet if it doesn't exist
            sh = await asyncio.to_thread(self.gc.create, "ASTA LinkedIn Pipeline")
            ws = sh.sheet1
            await asyncio.to_thread(
                ws.append_row,
                ["ID", "Content", "Hashtags", "Media URL", "Scheduled Time", "Status"]
            )
            logger.info("Created new ASTA LinkedIn Pipeline sheet")
            return ws
    
    async def add_post_row(
        self,
        content: str,
        hashtags: str,
        media_url: str = "",
        scheduled_time: str = "",
        status: str = "Draft"
    ) -> str:
        """Add a new post row to the sheet. Returns row ID."""
        try:
            ws = await self._get_sheet()
            row_id = str(uuid.uuid4())[:8]
            await asyncio.to_thread(
                ws.append_row,
                [row_id, content, hashtags, media_url, scheduled_time, status]
            )
            logger.info(f"Added post row with ID: {row_id}")
            return row_id
        except Exception as e:
            logger.error(f"Failed to add post row: {e}")
            raise
    
    async def get_all_posts(self) -> list:
        """Get all posts from the sheet."""
        try:
            ws = await self._get_sheet()
            records = await asyncio.to_thread(ws.get_all_records)
            return records
        except Exception as e:
            logger.error(f"Failed to get all posts: {e}")
            return []
    
    async def update_post_status(self, row_id: str, status: str) -> bool:
        """Update the status of a post by row ID."""
        try:
            ws = await self._get_sheet()
            records = await asyncio.to_thread(ws.get_all_records)
            for i, r in enumerate(records, start=2):  # Start at 2 (skip header)
                if r.get("ID") == row_id:
                    await asyncio.to_thread(ws.update_cell, i, 6, status)
                    logger.info(f"Updated post {row_id} status to {status}")
                    return True
            logger.warning(f"Post with ID {row_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to update post status: {e}")
            return False


# Global instance
sheets_service = SheetsService()
