"""
SearchTool â€” Web search via Serper API.

Operations: search, deep_search, search_papers
Provider: Serper API (SERPER_API env var)
Cache: LRU 1 hour for identical queries
"""

import asyncio
import logging
import os
import time
from functools import lru_cache
from typing import Optional

import httpx

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("SearchTool")

SERPER_API_KEY = os.getenv("SERPER_API", "")
SERPER_BASE_URL = "https://google.serper.dev"
MAX_QUERY_LENGTH = 200
TIMEOUT = 10.0
MAX_RETRIES = 3

# Simple in-memory cache: query â†’ (timestamp, results)
_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL = 3600  # 1 hour


def _cache_get(key: str) -> Optional[list]:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _cache_set(key: str, data: list):
    _cache[key] = (time.time(), data)
    # Evict old entries if cache gets too large
    if len(_cache) > 512:
        oldest = sorted(_cache.items(), key=lambda x: x[1][0])[:100]
        for k, _ in oldest:
            _cache.pop(k, None)


class SearchTool(BaseTool):
    name = "search"
    description = "Web search, deep search with content fetch, and academic paper search via Serper API."

    async def validate(self, payload: dict) -> tuple[bool, str]:
        operation = payload.get("operation", "")
        if operation not in ("search", "deep_search", "search_papers", "arxiv_search"):
            return False, f"Invalid operation '{operation}'. Must be: search, deep_search, search_papers, arxiv_search"

        query = payload.get("query", "").strip()
        if not query:
            return False, "Missing 'query' field"
        if len(query) > MAX_QUERY_LENGTH:
            return False, f"Query too long ({len(query)} chars). Max: {MAX_QUERY_LENGTH}"

        if operation in ("search", "deep_search", "search_papers") and not SERPER_API_KEY:
            return False, "SERPER_API not configured in environment"

        return True, ""

    async def execute(self, payload: dict) -> dict:
        operation = payload["operation"]
        query = payload["query"].strip()
        num_results = payload.get("num_results", 5)

        if operation == "search":
            return await self._search(query, num_results)
        elif operation == "deep_search":
            return await self._deep_search(query)
        elif operation == "search_papers":
            return await self._search_papers(query, num_results)
        elif operation == "arxiv_search":
            return await self._arxiv_search(query, num_results)
        else:
            return {"error": f"Unknown operation: {operation}"}

    async def _search(self, query: str, num_results: int = 5) -> dict:
        """Standard web search."""
        cache_key = f"search:{query}:{num_results}"
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.info(f"[Search] Cache hit for: '{query[:30]}'")
            return {"data": cached, "message": f"{len(cached)} results (cached)"}

        results = await self._serper_search(query, num_results)
        if "error" in results:
            return results

        _cache_set(cache_key, results["data"])
        return results

    async def _deep_search(self, query: str) -> dict:
        """Search + fetch full page content for top 3 results."""
        search_result = await self._search(query, 10)
        if "error" in search_result:
            return search_result

        items = search_result.get("data", [])[:3]
        enriched = []

        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            for item in items:
                url = item.get("url", "")
                try:
                    resp = await client.get(url, headers={"User-Agent": "ASTA/2.0"})
                    # Extract text content (simple: strip HTML tags)
                    text = resp.text
                    # Very basic HTML to text
                    import re
                    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    item["full_content"] = text[:3000]  # Cap at 3000 chars
                except Exception as e:
                    item["full_content"] = f"Failed to fetch: {e}"
                enriched.append(item)

        return {"data": enriched, "message": f"{len(enriched)} results with content"}

    async def _search_papers(self, query: str, num_results: int = 5) -> dict:
        """Academic paper search — adds research modifiers to query."""
        academic_query = f"{query} research paper filetype:pdf OR site:arxiv.org"
        return await self._search(academic_query, num_results)

    async def _arxiv_search(self, query: str, num_results: int = 5) -> dict:
        """Query official arXiv API using XML endpoint."""
        import urllib.parse
        import xml.etree.ElementTree as ET
        
        # Clean query: replace spaces with '+'
        safe_query = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{safe_query}&max_results={num_results}"
        
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                xml_data = resp.text
                
            # Parse XML
            root = ET.fromstring(xml_data)
            
            # Arxiv uses atom namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            results = []
            for entry in root.findall('atom:entry', ns):
                title_elem = entry.find('atom:title', ns)
                summary_elem = entry.find('atom:summary', ns)
                id_elem = entry.find('atom:id', ns)
                published_elem = entry.find('atom:published', ns)
                
                title = title_elem.text.strip() if title_elem is not None else "Unknown Title"
                # Strip excessive newlines in titles often found in arXiv metadata
                title = " ".join(title.split())
                
                summary = summary_elem.text.strip() if summary_elem is not None else "No summary available."
                summary = " ".join(summary.split())
                
                paper_id = id_elem.text.strip() if id_elem is not None else ""
                published = published_elem.text.strip() if published_elem is not None else ""
                
                authors = []
                for author_elem in entry.findall('atom:author', ns):
                    name_elem = author_elem.find('atom:name', ns)
                    if name_elem is not None:
                        authors.append(name_elem.text.strip())
                
                results.append({
                    "title": title,
                    "url": paper_id,
                    "snippet": summary[:500] + ("..." if len(summary) > 500 else ""),
                    "authors": authors,
                    "published": published,
                })
                
            return {"data": results, "message": f"{len(results)} papers found"}
        except Exception as e:
            logger.error(f"[SearchTool] Arxiv query failed: {e}")
            return {"error": f"Arxiv search failed: {e}"}

    async def _serper_search(self, query: str, num_results: int) -> dict:
        """Call Serper API with retry."""
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        }
        body = {"q": query, "num": num_results}

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(
                        f"{SERPER_BASE_URL}/search",
                        json=body,
                        headers=headers,
                    )

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(f"[Search] Rate limited. Retrying in {wait}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    organic = data.get("organic", [])
                    results = [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("link", ""),
                            "snippet": r.get("snippet", ""),
                            "position": r.get("position", 0),
                        }
                        for r in organic[:num_results]
                    ]

                    return {"data": results, "message": f"{len(results)} results"}

            except httpx.TimeoutException:
                logger.warning(f"[Search] Timeout (attempt {attempt + 1})")
                if attempt == MAX_RETRIES - 1:
                    return {"error": "Search timed out after retries"}
            except Exception as e:
                logger.error(f"[Search] API error: {e}")
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"Search failed: {e}"}
                await asyncio.sleep(2 ** attempt)

        return {"error": "Search failed after max retries"}
