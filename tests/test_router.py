import pytest
import pytest_asyncio
import asyncio
from backend.app.core.llm_factory import QuotaLedger, CircuitBreaker, Provider, Router, LLMResult

class MockProvider(Provider):
    def __init__(self, name: str, should_fail=False):
        super().__init__(name)
        self.should_fail = should_fail
        self.calls = 0

    async def chat(self, model: str, messages: list, tools=None, **kw) -> LLMResult:
        self.calls += 1
        if self.should_fail:
            raise Exception("Rate limit exceeded")
        return LLMResult(text=f"Hello from {self.name}", total_tokens=10)

@pytest.fixture
def mock_redis(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.data = {}
        async def incrby(self, key, val):
            self.data[key] = self.data.get(key, 0) + val
        async def get(self, key):
            return self.data.get(key)
            
    fake = FakeRedis()
    
    # Patch redis.asyncio.from_url to return our fake
    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url", lambda url: fake)
    return fake

@pytest.mark.asyncio
async def test_quota_ledger(mock_redis):
    ledger = QuotaLedger("redis://fake")
    await ledger.spend("groq", 100)
    
    headroom = await ledger.headroom("groq")
    # 500000 is limit for groq
    assert headroom == (1.0 - (100 / 500000))
    
    await ledger.spend("groq", 499900)
    headroom2 = await ledger.headroom("groq")
    assert headroom2 == 0.0

def test_circuit_breaker():
    cb = CircuitBreaker()
    assert not cb.open
    cb.trip(cooldown=1)
    assert cb.open

@pytest.mark.asyncio
async def test_router_fallback(mock_redis, monkeypatch):
    router = Router("redis://fake")
    
    p1 = MockProvider("groq", should_fail=True)
    p2 = MockProvider("gemini", should_fail=False)
    
    router.providers = {"groq": p1, "gemini": p2}
    
    res = await router.run("realtime_chat", [{"role": "user", "content": "hi"}])
    
    assert res.text == "Hello from gemini"
    assert p1.calls == 1
    assert p2.calls == 1
    assert p1.breaker.open # groq should be tripped
    
    # Second call should skip groq entirely
    res2 = await router.run("realtime_chat", [{"role": "user", "content": "hi"}])
    assert res2.text == "Hello from gemini"
    assert p1.calls == 1 # still 1
    assert p2.calls == 2
