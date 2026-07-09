"""
LLM Factory — single place to get a completion with provider fallback.

Primary: Groq (Llama 3.x). Fallback: Google Gemini (if GEMINI_API_KEY set).
Used by the supervisor graph and workflow nodes so model selection and
fallback logic live in ONE place.
"""
import logging
import asyncio
from typing import Optional, Dict, Any, List
import redis.asyncio as aioredis
from pydantic import BaseModel
from backend.app.config import settings

logger = logging.getLogger("LLMFactory")

class LLMResult(BaseModel):
    text: str
    total_tokens: int = 0
    raw_response: Any = None

class QuotaLedger:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
        
    async def spend(self, provider: str, tokens: int):
        try:
            await self.redis.incrby(f"quota:{provider}:tokens_today", tokens)
        except Exception as e:
            logger.warning(f"Failed to update quota ledger: {e}")
        
    async def headroom(self, provider: str) -> float:
        # Simplistic implementation: hardcoded daily limits
        limits = {
            "groq": 500000,
            "gemini": 1000000,
            "ollama": float("inf")
        }
        try:
            spent = await self.redis.get(f"quota:{provider}:tokens_today")
            spent = int(spent) if spent else 0
        except Exception as e:
            logger.warning(f"Failed to read quota ledger: {e}")
            spent = 0
            
        limit = limits.get(provider, 100000)
        return max(0.0, 1.0 - (spent / limit))

class CircuitBreaker:
    def __init__(self):
        self.open_until = 0.0

    @property
    def open(self):
        import time
        return time.time() < self.open_until

    def trip(self, cooldown: int = 60):
        import time
        self.open_until = time.time() + cooldown

class Provider:
    def __init__(self, name: str):
        self.name = name
        self.breaker = CircuitBreaker()

    async def chat(self, model: str, messages: list, tools=None, **kw) -> LLMResult:
        raise NotImplementedError

    async def stt(self, model: str, audio: bytes, **kw) -> str:
        raise NotImplementedError

class GroqProvider(Provider):
    def __init__(self):
        super().__init__("groq")
        if settings.GROQ_API_KEY:
            from groq import AsyncGroq
            self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        else:
            self.client = None

    async def stt(self, model: str, audio: bytes, **kw) -> str:
        if not self.client:
            raise Exception("Groq not configured")
        import io
        file_obj = ("audio.wav", io.BytesIO(audio), "audio/wav")
        resp = await self.client.audio.transcriptions.create(
            file=file_obj,
            model=model,
            prompt=kw.get("prompt", ""),
            language=kw.get("language")
        )
        return resp.text

    async def chat(self, model: str, messages: list, tools=None, **kw) -> LLMResult:
        if not self.client:
            raise Exception("Groq not configured")
        resp = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kw.get("temperature", 0.7),
            max_tokens=kw.get("max_tokens", 1024),
        )
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else int(len(text)/4)
        return LLMResult(text=text.strip(), total_tokens=tokens, raw_response=resp)

class GeminiProvider(Provider):
    def __init__(self):
        super().__init__("gemini")
        if settings.GEMINI_API_KEY:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.configured = True
        else:
            self.configured = False

    async def chat(self, model: str, messages: list, tools=None, **kw) -> LLMResult:
        if not self.configured:
            raise Exception("Gemini not configured")
        import google.generativeai as genai
        gemini_model = genai.GenerativeModel(model)
        
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        prompt = f"{sys_msg}\n\n" + "\n".join(user_msgs)
        
        resp = await asyncio.to_thread(gemini_model.generate_content, prompt)
        text = resp.text or ""
        tokens = int(len(text)/4) 
        return LLMResult(text=text.strip(), total_tokens=tokens, raw_response=resp)

    async def stt(self, model: str, audio: bytes, **kw) -> str:
        if not self.configured:
            raise Exception("Gemini not configured")
        import google.generativeai as genai
        gemini_model = genai.GenerativeModel("gemini-1.5-flash") # best for audio
        prompt = kw.get("prompt", "Transcribe this audio")
        # Audio bytes upload to Gemini needs specific handling; stubbed for fallback
        # In a real impl, we'd upload blob or pass inline data.
        resp = await asyncio.to_thread(
            gemini_model.generate_content,
            [prompt, {"mime_type": "audio/wav", "data": audio}]
        )
        return resp.text

CHAINS = {
    "realtime_chat": [("groq", "llama-3.3-70b-versatile"), ("gemini", "gemini-2.5-flash")],
    "stt": [("groq", "whisper-large-v3-turbo")],
    "extraction": [("groq", "llama-3.3-70b-versatile"), ("gemini", "gemini-2.5-flash")],
    "default": [("groq", "llama-3.1-8b-instant"), ("gemini", "gemini-2.5-flash")]
}

SHED_FLOOR = {
    "realtime_chat": 0.2,
    "stt": 0.1,
    "extraction": 0.5,
    "default": 0.0
}

class Router:
    def __init__(self, redis_url: str):
        self.ledger = QuotaLedger(redis_url)
        self.providers = {
            "groq": GroqProvider(),
            "gemini": GeminiProvider()
        }

    async def run(self, task: str, messages: list = None, audio: bytes = None, **kw) -> Any:
        chain = CHAINS.get(task, CHAINS["default"])
        shed_floor = SHED_FLOOR.get(task, 0.0)

        for prov_name, model in chain:
            prov = self.providers.get(prov_name)
            if not prov: continue
            
            if prov.breaker.open: continue
            
            headroom = await self.ledger.headroom(prov.name)
            if headroom < shed_floor:
                logger.warning(f"Shedding load for {task} on {prov.name} (headroom {headroom:.2f} < {shed_floor})")
                continue

            try:
                if audio is not None and task == "stt":
                    text = await prov.stt(model, audio, **kw)
                    # Rough token estimation for audio: seconds * 2
                    await self.ledger.spend(prov.name, 100) # placeholder
                    return text
                else:
                    r = await prov.chat(model, messages or [], **kw)
                    await self.ledger.spend(prov.name, r.total_tokens)
                    return r
            except Exception as e:
                err_str = str(e).lower()
                if "rate limit" in err_str or "429" in err_str:
                    logger.warning(f"Rate limited on {prov.name}. Tripping breaker for 60s.")
                    prov.breaker.trip(cooldown=60)
                else:
                    logger.warning(f"Provider {prov.name} failed: {e}. Tripping breaker for 30s.")
                    prov.breaker.trip(cooldown=30)
                continue
                
        raise Exception("All providers exhausted or rate-limited.")

router = Router(settings.REDIS_URL or "redis://localhost:6379/0")

async def acomplete(
    system: str,
    user: str,
    task: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]
    try:
        res = await router.run(task, messages, temperature=temperature, max_tokens=max_tokens)
        return res.text
    except Exception as e:
        logger.error(f"[LLMFactory] {e}")
        return "Sorry boss, my language models are unreachable right now."
