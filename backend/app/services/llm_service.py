import logging
import asyncio
from groq import AsyncGroq, RateLimitError
from backend.app.config import config as settings
from typing import AsyncGenerator

logger = logging.getLogger("LLM_Stream")
client = AsyncGroq(api_key=settings.GROQ_API_KEY)

def get_system_prompt(health_status: str = "full"):
    mode_notice = ""
    if health_status == "local_only":
        mode_notice = "\n[SYSTEM NOTICE: Operating in Local-Only mode. Long-term memory unavailable.]"
    elif health_status == "degraded_l3":
        mode_notice = "\n[SYSTEM NOTICE: Graph memory degraded. Using vector search only.]"
    elif health_status == "degraded_l2_l3":
        mode_notice = "\n[SYSTEM NOTICE: Archival memory degraded. Relying on conversation history only.]"
    
    return f"""You are ASTA, a real-time voice AI assistant.
Respond conversationally as if spoken aloud. No markdown, no bullet points, and no lists.
Keep your first sentence extremely short (under 10 words).
Be ultra-concise and warm. Zero tolerance for hallucinations. 
The immediate back-and-forth messages (L1 Context) are Absolute Truth regarding current anaphora ("it", "he", "that"). 
Any injected "SYSTEM CONTEXT AND MEMORY" contains the User's current definitive identity, skills, projects, and relevant historical context. Treat the [USER PROFILE / IDENTITY] as Absolute Truth.
    """
    
def get_hydrated_messages(user_message: str, history: list[dict] | None = None, rag_context: str | None = None, health_status: str = "full"):
    """
    Constructs the exact LLM inference arrays enforcing "Context-First" weightings.
    Prioritizes L1 active rolling buffers over L2/L3 archival data.
    Injects health status so LLM knows when operating in degraded mode.
    """
    messages = [{"role": "system", "content": get_system_prompt(health_status)}]
    
    # 1. Hot-Path L1 Fluid Injection (Recent conversational memory bounds)
    if history:
        messages.extend(history)
        
    # 2. RAG Supplemental Knowledge Overlay (L2/L3 Data)
    if rag_context:
        augmented_prompt = f"SYSTEM CONTEXT AND MEMORY:\n{rag_context}\n\nUSER'S IMMEDIATE QUERY: {user_message}"
    else:
        augmented_prompt = user_message
        
    messages.append({"role": "user", "content": augmented_prompt})
    
    return messages

async def stream_llm_response(
    user_message: str,
    session_id: str | None = None,
    history: list[dict] | None = None,
    rag_context: str | None = None,
    health_status: str = "full"
) -> AsyncGenerator[str, None]:

    messages = get_hydrated_messages(user_message, history, rag_context, health_status)
    
    # 429 Resilience: Fast failback for real-time streaming
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # 3. Inference Stream Map
            stream = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                stream=True,
                max_tokens=300,
                temperature=0.7,
            )
            
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            return  # Success - exit function
            
        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 0.5 * (attempt + 1)  # 0.5s
                logger.warning(f"[LLM] Rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                yield "System: Please wait, I'm recalibrating..."
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"[LLM] Rate limit exceeded after {max_retries} attempts")
                yield "System: I'm currently overloaded. Please try again shortly."
                return
        except Exception as e:
            logger.error(f"[LLM] Unexpected error: {e}")
            raise
