import os
import gc
import json
import logging
import asyncio
from groq import AsyncGroq
from backend.app.config import config

logger = logging.getLogger(__name__)

# Initialize Groq client
client = AsyncGroq(api_key=config.GROQ_API_KEY)

async def stream_groq_llm(messages, temperature=0.7):
    """
    Directly connects to Groq and pure-streams the response tokens.
    Takes standard OpenAI/Groq message list: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    try:
        stream = await client.chat.completions.create(
            messages=messages,
            model=config.MODEL_NAME, # 'llama-3.3-70b-versatile'
            temperature=temperature,
            stream=True,
            max_tokens=1024
        )
        
        async for chunk in stream:
            # Yield tokens as they arrive
            token = chunk.choices[0].delta.content
            if token is not None:
                yield token
                
    except asyncio.CancelledError:
        logger.warning("LLM stream cancelled by system.")
        raise
    except Exception as e:
        logger.error(f"Error in stream_groq_llm: {e}")
        yield " I'm sorry, I encountered an error."
