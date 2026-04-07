from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import hashlib
import importlib
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheService:
    """Redis-first cache with in-memory TTL fallback."""

    _redis = None
    _enabled = False
    _memory: dict[str, tuple[float, str]] = {}
    _hits = 0
    _misses = 0

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha1((raw or "").encode("utf-8")).hexdigest()

    @classmethod
    def _namespaced_key(cls, namespace: str, key: str) -> str:
        ns = (namespace or "default").strip().lower()
        return f"{ns}:{key}"

    @classmethod
    async def connect(cls):
        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            logger.info("[CACHE] REDIS_URL missing, using in-memory cache fallback")
            cls._enabled = True
            return

        try:
            redis = importlib.import_module("redis.asyncio")
            cls._redis = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            await cls._redis.ping()
            cls._enabled = True
            logger.info("[CACHE] Redis connected")
        except Exception as exc:
            logger.warning("[CACHE] Redis unavailable, fallback to memory cache: %s", exc)
            cls._redis = None
            cls._enabled = True

    @classmethod
    async def close(cls):
        if cls._redis is not None:
            await cls._redis.aclose()
        cls._redis = None

    @classmethod
    async def get_json(cls, key: str) -> Optional[Any]:
        if not cls._enabled:
            return None

        if cls._redis is not None:
            try:
                raw = await cls._redis.get(key)
                if not raw:
                    cls._misses += 1
                    return None
                cls._hits += 1
                return json.loads(raw)
            except Exception:
                cls._misses += 1
                return None

        item = cls._memory.get(key)
        if not item:
            cls._misses += 1
            return None
        expires_at, payload = item
        if expires_at < time.time():
            cls._memory.pop(key, None)
            cls._misses += 1
            return None
        try:
            cls._hits += 1
            return json.loads(payload)
        except Exception:
            cls._misses += 1
            return None

    @classmethod
    async def set_json(cls, key: str, value: Any, ttl_seconds: int = 300):
        if not cls._enabled:
            return

        payload = json.dumps(value, default=str)
        ttl_seconds = max(1, int(ttl_seconds))

        if cls._redis is not None:
            try:
                await cls._redis.set(key, payload, ex=ttl_seconds)
                return
            except Exception:
                pass

        cls._memory[key] = (time.time() + ttl_seconds, payload)

    @classmethod
    async def get_or_set_json(cls, key: str, producer_coro, ttl_seconds: int = 300):
        cached = await cls.get_json(key)
        if cached is not None:
            return cached
        value = await producer_coro()
        await cls.set_json(key, value, ttl_seconds)
        return value

    @classmethod
    async def get_embedding_cache(cls, text: str):
        key = cls._namespaced_key("embedding", cls.hash_key(text))
        return await cls.get_json(key)

    @classmethod
    async def set_embedding_cache(cls, text: str, embedding: Any, ttl_seconds: int = 86400):
        key = cls._namespaced_key("embedding", cls.hash_key(text))
        await cls.set_json(key, embedding, ttl_seconds)

    @classmethod
    async def get_retrieval_cache(cls, query: str, top_k: int):
        key = cls._namespaced_key("retrieval", cls.hash_key(f"{query}|{top_k}"))
        return await cls.get_json(key)

    @classmethod
    async def set_retrieval_cache(cls, query: str, top_k: int, results: Any, ttl_seconds: int = 300):
        key = cls._namespaced_key("retrieval", cls.hash_key(f"{query}|{top_k}"))
        await cls.set_json(key, results, ttl_seconds)

    @classmethod
    async def get_session_cache(cls, session_id: str):
        key = cls._namespaced_key("session", session_id)
        return await cls.get_json(key)

    @classmethod
    async def set_session_cache(cls, session_id: str, session_data: Any, ttl_seconds: int = 900):
        key = cls._namespaced_key("session", session_id)
        await cls.set_json(key, session_data, ttl_seconds)

    @classmethod
    async def delete_session_cache(cls, session_id: str):
        key = cls._namespaced_key("session", session_id)
        if cls._redis is not None:
            try:
                await cls._redis.delete(key)
            except Exception:
                pass
        cls._memory.pop(key, None)

    @classmethod
    def get_cache_stats(cls) -> dict[str, Any]:
        total = cls._hits + cls._misses
        hit_rate = (cls._hits / total) if total > 0 else 0.0
        return {
            "enabled": bool(cls._enabled),
            "backend": "redis" if cls._redis is not None else "memory",
            "hits": cls._hits,
            "misses": cls._misses,
            "hit_rate": hit_rate,
            "memory_items": len(cls._memory),
        }
