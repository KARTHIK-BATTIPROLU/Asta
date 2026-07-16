import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.core.llm_factory import router, GroqProvider, GeminiProvider

@pytest.mark.asyncio
async def test_router_fallback():
    # Verify that if Groq rate-limits, the circuit breaker trips and Gemini is used
    messages = [{"role": "user", "content": "hello"}]
    
    # Mock Groq to fail with rate limit
    with patch("backend.app.core.llm_factory.GroqProvider.chat") as mock_groq_chat:
        mock_groq_chat.side_effect = Exception("Rate limit exceeded 429")
        
        # Mock Gemini to succeed
        with patch("backend.app.core.llm_factory.GeminiProvider.chat") as mock_gemini_chat:
            mock_gemini_chat_result = MagicMock()
            mock_gemini_chat_result.text = "Hello from Gemini"
            mock_gemini_chat_result.total_tokens = 10
            mock_gemini_chat.return_value = mock_gemini_chat_result
            
            # Reset circuit breakers
            for p in router.providers.values():
                p.breaker.open_until = 0.0
                
            res = await router.run(task="default", messages=messages)
            
            # Groq should have been called first
            mock_groq_chat.assert_called_once()
            
            # Gemini should have been called next
            mock_gemini_chat.assert_called_once()
            
            # Circuit breaker for Groq should be open
            groq_provider = router.providers["groq"]
            assert groq_provider.breaker.open is True
            
            assert res.text == "Hello from Gemini"
