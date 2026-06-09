"""
LLM Factory — single place to get a completion with provider fallback.

Primary: Groq (Llama 3.x). Fallback: Google Gemini (if GEMINI_API_KEY set).
Used by the supervisor graph and workflow nodes so model selection and
fallback logic live in ONE place.
"""
import logging
from typing import Optional

from groq import AsyncGroq

from backend.app.config import settings

logger = logging.getLogger("LLMFactory")

# Task → Groq model. Fast model for classification, larger for generation.
_GROQ_MODELS = {
    "classify": "llama-3.1-8b-instant",
    "quick": "llama-3.1-8b-instant",
    "generate": "llama-3.3-70b-versatile",
    "default": "llama-3.1-8b-instant",
}

_groq_client: Optional[AsyncGroq] = None


def _get_groq() -> Optional[AsyncGroq]:
    """Lazily build the Groq client (None if no key configured)."""
    global _groq_client
    if _groq_client is None and settings.GROQ_API_KEY:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _groq_client


async def _try_groq(system: str, user: str, task: str, temperature: float, max_tokens: int) -> Optional[str]:
    client = _get_groq()
    if not client:
        return None
    model = _GROQ_MODELS.get(task, _GROQ_MODELS["default"])
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


async def _try_gemini(system: str, user: str) -> Optional[str]:
    """Fallback to Gemini Flash when Groq is unavailable."""
    if not settings.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        # Gemini has no separate system role; prepend it.
        prompt = f"{system}\n\n{user}" if system else user
        import asyncio
        resp = await asyncio.to_thread(model.generate_content, prompt)
        return (resp.text or "").strip()
    except Exception as e:
        logger.error(f"[LLMFactory] Gemini fallback failed: {e}")
        return None


async def acomplete(
    system: str,
    user: str,
    task: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """
    Get a completion. Tries Groq first, then Gemini.
    Never raises — returns a safe message on total failure.
    """
    # 1. Primary: Groq
    try:
        out = await _try_groq(system, user, task, temperature, max_tokens)
        if out:
            return out
    except Exception as e:
        logger.warning(f"[LLMFactory] Groq failed ({task}): {e} — trying fallback")

    # 2. Fallback: Gemini
    out = await _try_gemini(system, user)
    if out:
        return out

    logger.error("[LLMFactory] All providers failed.")
    return "Sorry boss, my language models are unreachable right now."


# Convenience export
llm = acomplete
