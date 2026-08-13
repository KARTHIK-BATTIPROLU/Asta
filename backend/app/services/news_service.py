"""
ASTA News Service
Fetches top headlines from Hacker News and arXiv cs.AI via RSS.
"""
import logging
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class NewsService:
    async def _fetch_rss_titles(self, url: str, limit: int = 2) -> list[str]:
        """Fetch RSS feed and parse out item titles."""
        titles = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, "xml")
                    items = soup.find_all("item")
                    for item in items[:limit]:
                        title = item.find("title")
                        if title:
                            titles.append(title.text)
        except Exception as e:
            logger.error(f"Failed to fetch RSS from {url}: {e}")
        return titles

    async def get_morning_headlines(self) -> str:
        """Fetch 2-3 top headlines for the morning brief."""
        hn_url = "https://hnrss.org/frontpage"
        arxiv_url = "http://export.arxiv.org/rss/cs.AI"
        
        hn_titles = await self._fetch_rss_titles(hn_url, limit=2)
        arxiv_titles = await self._fetch_rss_titles(arxiv_url, limit=1)
        
        brief = []
        if hn_titles:
            brief.append("From Hacker News:")
            for t in hn_titles:
                brief.append(f"- {t}")
        if arxiv_titles:
            brief.append("From arXiv AI:")
            for t in arxiv_titles:
                brief.append(f"- {t}")
                
        if not brief:
            return "No news updates fetched today."
            
        return "\n".join(brief)

news_service = NewsService()
