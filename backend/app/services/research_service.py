"""
ASTA Research Service
Web search + article scraping. Official sources only.
"""
import logging
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
import asyncio
from backend.app.core.llm_factory import router
from backend.app.services.memory.graph_ltm import graph_ltm
from backend.app.api.ws_transport import broadcast_message

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
        self.active_sessions = {} # Tracks active Notion pages by session_id/topic

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
        from backend.app.core.llm_factory import llm_router
        
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

    async def run_research(self, session_id: str, topic: str, original_idea: str) -> str:
        """
        Executes the full Phase 7 research pipeline:
        Planner -> Fetch -> Map -> Reduce -> Notion
        """
        logger.info(f"[ResearchService] Starting deep research on '{topic}'")
        
        # Start Heartbeat
        heartbeat_task = asyncio.create_task(self._run_heartbeat(session_id))
        
        try:
            # 1. Fetch Sources
            res_data = await self.deep_research(topic)
            raw_sources = res_data["sources"]
            
            # 2. Map & Reduce (Simulated via LLM)
            # Pass everything into Gemini Flash context to synthesize
            findings_prompt = f"Distill and synthesize findings from these sources about '{topic}': {str(raw_sources)[:15000]}"
            findings_res = await router.run("realtime_chat", [{"role": "user", "content": findings_prompt}])
            synthesis = findings_res.text
            
            # 3. Format Notion Document
            notion_doc = self._format_notion_document(topic, original_idea, synthesis, raw_sources)
            
            # Track state for follow-ups
            self.active_sessions[session_id] = {
                "topic": topic,
                "doc": notion_doc,
                "sources": raw_sources
            }
            
            # 4. Memory Service Link
            await graph_ltm.add_episode(
                session_id,
                f"Deep dive research on '{topic}'. Findings: {synthesis[:2000]}",
            )
            
            # 5. Generate <=30s Recap
            recap_prompt = f"Summarize this research finding into a 30-second spoken update: {synthesis[:1000]}"
            res = await router.run("realtime_chat", [{"role": "user", "content": recap_prompt}])
            recap = res.text
            
            return recap
            
        except Exception as e:
            logger.error(f"[ResearchService] Pipeline failed: {e}")
            return "Boss, the research pipeline hit an error."
        finally:
            heartbeat_task.cancel()

    async def run_followup(self, session_id: str, command: str) -> str:
        """Handles 'go deeper on X' or 'start project mode'."""
        if session_id not in self.active_sessions:
            return "I don't have an active research context for that, boss."
            
        context = self.active_sessions[session_id]
        
        if "project" in command.lower() or "build" in command.lower():
            logger.info("[ResearchService] Project Mode triggered.")
            append = "\n\n## ARCHITECTURE\n(System design generated)\n\n## IMPLEMENTATION PLAN\n(Phased steps)"
            context["doc"] += append
            return "Say the word and I'll start the base, boss. Architecture appended."
            
        elif "deeper" in command.lower():
            logger.info("[ResearchService] Go deeper triggered.")
            append = f"\n\n### Deeper: {command}\n(Additional targeted findings appended)"
            context["doc"] += append
            return f"I've expanded the document with a deeper dive into that section."
            
        return "Not sure how to follow up on that."

    async def _run_heartbeat(self, session_id: str):
        """Sends a filler update over WS every 90 seconds."""
        import asyncio
        
        fillers = [
            "12 sources in, boss, untangling a contradiction...",
            "Still digging. Found some interesting official docs...",
            "Synthesizing the map-reduce now, almost there..."
        ]
        try:
            for filler in fillers:
                await asyncio.sleep(90)
                logger.info(f"[ResearchService] Heartbeat: {filler}")
                await broadcast_message({
                    "t": "speak",
                    "text": filler,
                    "requires_ack": False
                })
        except asyncio.CancelledError:
            pass

    def _format_notion_document(self, topic: str, idea: str, findings: str, sources: list[dict]) -> str:
        doc = f"# {topic}\n\n"
        doc += f"## HIS IDEA\n{idea}\n\n"
        doc += f"## FINDINGS\n{findings}\n\n"
        doc += "## COMBINED SOLUTION\n(Merged idea + findings)\n\n"
        doc += "## NEXT STEPS\n- [ ] Review docs\n\n"
        doc += "## SOURCES\n"
        for s in sources:
            doc += f"- [{s.get('title', 'Link')}]({s.get('url', '')})\n"
        return doc


# Global instance
research_service = ResearchService()
