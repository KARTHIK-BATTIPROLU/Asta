"""
Rate Limiter — Token bucket for WebSocket connections.

Prevents a single client from flooding the LLM pipeline.
Each session gets its own bucket. Configurable burst + sustained rate.
"""

import time
import logging
from typing import Dict

logger = logging.getLogger("RateLimiter")


class TokenBucket:
    """
    Token bucket rate limiter for a single client.

    Args:
        rate: Tokens added per second (sustained rate)
        burst: Maximum tokens (burst capacity)
    """

    def __init__(self, rate: float = 1.0, burst: int = 5):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens. Returns True if allowed, False if rate limited.
        """
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        # Refill tokens based on elapsed time
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)

        if self._tokens >= tokens:
            self._tokens -= tokens
            return True

        return False

    @property
    def available(self) -> float:
        return self._tokens


class SessionRateLimiter:
    """
    Per-session rate limiter.
    Creates a TokenBucket for each session_id automatically.

    Defaults:
        - 1 turn per second sustained
        - Burst of 5 rapid turns allowed
    """

    def __init__(self, rate: float = 1.0, burst: int = 5):
        self.rate = rate
        self.burst = burst
        self._buckets: Dict[str, TokenBucket] = {}

    def check(self, session_id: str) -> bool:
        """Check if this session is allowed to proceed."""
        if session_id not in self._buckets:
            self._buckets[session_id] = TokenBucket(self.rate, self.burst)
        return self._buckets[session_id].consume()

    def cleanup(self, session_id: str):
        """Remove bucket on session close."""
        self._buckets.pop(session_id, None)

    def cleanup_stale(self, max_idle: float = 300.0):
        """Remove buckets for sessions idle > max_idle seconds."""
        now = time.monotonic()
        stale = [
            sid for sid, bucket in self._buckets.items()
            if now - bucket._last_refill > max_idle
        ]
        for sid in stale:
            del self._buckets[sid]


# Global instance — 1 turn/sec sustained, 5 burst
ws_rate_limiter = SessionRateLimiter(rate=1.0, burst=5)
