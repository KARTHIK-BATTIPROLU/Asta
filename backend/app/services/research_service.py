"""
ASTA Research Service
Web search + article scraping. Official sources only.
"""
import logging
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Allowed domains for research
ALLOWED_DOMAINS = {
    "arxiv.org", "docs.python.org", "docs.microsoft.com", "developer.mozilla.org",
    "react.dev", "nextjs.org", "fastapi.tiangolo.com", "pytorch.org", "tensorflow.org",
    "huggingface.co", "openai.com", "anthropic.com", "deepmind.google", "research.google",
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "techcrunch.com", "theverge.com",
    "wired.com", "nature.com", "science.org", "ieee.org", "acm.org",
    "github.com", "developer.apple.com", "developer.android.com",
    "cloud.google.com", "docs.aws.amazon.com", "learn.microsoft.com",
    "timesofindia.com", "ndtv.com", "thehindu.com", "economictimes.indiatimes.com",
    "python.org", "kubernetes.io", "docker.com", "redis.io", "mongodb.com", "neo4j.com",
    "langchain.com", "python.langchain.com", "js.langchain.com",
}


def _is_allowed(url: str) -> bool:
    """Check if URL domain is in allowed list."""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)
    except:
        return False


class ResearchService:
    """Service for web research and content scraping."""
    
    def __init__(self):
        """Initialize HTTP client."""
        self.http_client = httpx.AsyncClient(
            timeout=settings.EXTERNAL_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "ASTA-Research/1.0"}
        )

    async def search(self, query: str, num_results: int = 10) -> list:
        """Serper API search. Returns only allowed-domain results."""
        try:
            response = await self.http_client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": settings.SERPER_API,
                    "Content-Type": "application/json"
                },
                json={"q": query, "num": num_results}
            )
            data = response.json()
            results = []
            for item in data.get("organic", []):
                url = item.get("link", "")
                if _is_allowed(url):
                    results.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "snippet": item.get("snippet", ""),
                    })
            logger.info(
                f"Search '{query}': {len(data.get('organic',[]))} total, "
                f"{len(results)} allowed"
            )
            return results
        except Exception as e:
            logger.error(f"Serper search failed: {e}")
            return []

    async def scrape_url(self, url: str) -> dict:
        """Scrape a URL. Returns cleaned text content."""
        if not _is_allowed(url):
            return {
                "url": url,
                "content": "",
                "success": False,
                "error": "Domain not allowed"
            }
        try:
            resp = await self.http_client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Remove noise
            for tag in soup([
                "script", "style", "nav", "footer", "header", "aside",
                "advertisement", ".cookie-banner", "[class*='ad-']"
            ]):
                tag.decompose()
            
            # Extract main content
            main = soup.find("article") or soup.find("main") or soup.find("body")
            if not main:
                return {
                    "url": url,
                    "content": "",
                    "success": False,
                    "error": "No content found"
                }
            
            text = " ".join(main.get_text(separator=" ").split())
            text = text[:8000]
            
            title = soup.find("title")
            title_text = title.get_text().strip() if title else ""
            
            return {
                "url": url,
                "title": title_text,
                "content": text,
                "success": True
            }
        except Exception as e:
            logger.error(f"Scrape failed for {url}: {e}")
            return {
                "url": url,
                "content": "",
                "success": False,
                "error": str(e)
            }

    async def deep_research(self, topic: str, extra_queries: list = None) -> dict:
        """Full research pipeline. Returns aggregated sources."""
        from backend.app.core.llm_router import llm_router
        
        # Generate search queries if not provided
        if not extra_queries:
            q_result = await llm_router.invoke_with_system(
                "intent_classification",
                "Generate 4 precise web search queries for researching this topic "
                "from official sources. Return only the queries, one per line, no numbering.",
                topic
            )
            queries = [q.strip() for q in q_result.strip().split("\n") if q.strip()][:4]
        else:
            queries = extra_queries[:4]
        
        all_sources = {}
        for query in queries:
            results = await self.search(query, num_results=5)
            for r in results[:3]:
                url = r["url"]
                if url not in all_sources:
                    scraped = await self.scrape_url(url)
                    if scraped["success"] and len(scraped["content"]) > 200:
                        all_sources[url] = {**r, "content": scraped["content"]}
        
        return {
            "topic": topic,
            "queries_used": queries,
            "sources": list(all_sources.values()),
            "total_sources": len(all_sources)
        }

    async def search_arxiv(self, topic: str) -> list:
        """Search arxiv for academic papers."""
        import urllib.parse
        import xml.etree.ElementTree as ET
        
        query = urllib.parse.quote(topic)
        try:
            resp = await self.http_client.get(
                f"http://export.arxiv.org/api/query?search_query=all:{query}"
                f"&max_results=5&sortBy=relevance"
            )
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            papers = []
            for entry in root.findall("atom:entry", ns):
                papers.append({
                    "title": entry.find("atom:title", ns).text.strip(),
                    "summary": entry.find("atom:summary", ns).text.strip()[:500],
                    "url": entry.find("atom:id", ns).text.strip(),
                    "published": entry.find("atom:published", ns).text[:10],
                })
            return papers
        except Exception as e:
            logger.error(f"Arxiv search failed: {e}")
            return []


# Global instance
research_service = ResearchService()
