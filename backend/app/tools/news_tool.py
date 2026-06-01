"""
NewsTool — Filtered news digest via Serper API news endpoint.

Operations: get_digest, get_topic, get_breaking
Provider: Serper API (SERPER_API env var)
Cache: 1 hour
"""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("NewsTool")

SERPER_API_KEY = os.getenv("SERPER_API", "")
SERPER_NEWS_URL = "https://google.serper.dev/news"
TIMEOUT = 10.0
MAX_RETRIES = 3

DEFAULT_TOPICS = ["technology", "artificial intelligence", "software development", "metaverse", "startups"]

# Cache: key → (timestamp, data)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 hour


def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _cache_set(key: str, data: dict):
    _cache[key] = (time.time(), data)


class NewsTool(BaseTool):
    name = "news"
    description = "Filtered tech news digest, topic search, and breaking news via Serper API."

    async def validate(self, payload: dict) -> tuple[bool, str]:
        operation = payload.get("operation", "")
        if operation not in ("get_digest", "get_topic", "get_breaking"):
            return False, f"Invalid operation '{operation}'. Must be: get_digest, get_topic, get_breaking"

        if not SERPER_API_KEY:
            return False, "SERPER_API not configured in environment"

        return True, ""

    async def execute(self, payload: dict) -> dict:
        operation = payload["operation"]

        if operation == "get_digest":
            topics = payload.get("topics", DEFAULT_TOPICS)
            num_per_topic = payload.get("num_per_topic", 2)
            return await self._get_digest(topics, num_per_topic)
        elif operation == "get_topic":
            topic = payload.get("topic", payload.get("query", "technology"))
            num = payload.get("num_results", 5)
            return await self._get_topic(topic, num)
        elif operation == "get_breaking":
            return await self._get_breaking()
        else:
            return {"error": f"Unknown operation: {operation}"}

    async def _get_digest(self, topics: list, num_per_topic: int = 2) -> dict:
        cache_key = f"digest:{':'.join(sorted(topics))}:{num_per_topic}"
        cached = _cache_get(cache_key)
        if cached:
            logger.info("[News] Cache hit for digest")
            return cached

        all_stories = []
        seen_titles = set()

        for topic in topics:
            topic_news = await self._serper_news(topic, num_per_topic + 2)  # Fetch extra for dedup
            if "error" in topic_news:
                continue

            count = 0
            for story in topic_news.get("data", []):
                title_lower = story["headline"].lower()
                if title_lower not in seen_titles and count < num_per_topic:
                    story["topic"] = topic
                    all_stories.append(story)
                    seen_titles.add(title_lower)
                    count += 1

        result = {
            "data": all_stories,
            "message": f"News digest: {len(all_stories)} stories across {len(topics)} topics",
        }
        _cache_set(cache_key, result)
        return result

    async def _get_topic(self, topic: str, num_results: int = 5) -> dict:
        cache_key = f"topic:{topic.lower()}:{num_results}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        result = await self._serper_news(topic, num_results)
        if "error" not in result:
            _cache_set(cache_key, result)
        return result

    async def _get_breaking(self) -> dict:
        cache_key = "breaking"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        result = await self._serper_news("breaking news technology", 5)
        if "error" not in result:
            _cache_set(cache_key, result)
        return result

    async def _serper_news(self, query: str, num: int) -> dict:
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        }
        body = {"q": query, "num": num}

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(SERPER_NEWS_URL, json=body, headers=headers)

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(f"[News] Rate limited. Retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    news = data.get("news", [])
                    stories = []
                    for item in news[:num]:
                        stories.append({
                            "headline": item.get("title", ""),
                            "summary": item.get("snippet", "")[:200],
                            "source": item.get("source", ""),
                            "url": item.get("link", ""),
                            "date": item.get("date", ""),
                        })

                    return {"data": stories, "message": f"{len(stories)} news results for '{query}'"}

            except httpx.TimeoutException:
                if attempt == MAX_RETRIES - 1:
                    return {"error": "News API timed out"}
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"News API failed: {e}"}
                await asyncio.sleep(2 ** attempt)

        return {"error": "News API failed after retries"}
