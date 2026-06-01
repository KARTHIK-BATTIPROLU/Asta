import logging
import asyncio
from groq import AsyncGroq, RateLimitError
from backend.app.config import config as settings
from typing import AsyncGenerator

logger = logging.getLogger("LLM_Stream")
client = AsyncGroq(api_key=settings.GROQ_API_KEY)

def get_system_prompt(health_status: str = "full", memory_context: str = ""):
    # ASTA Personality (added for memory integration)
    ASTA_PERSONALITY = """You are ASTA — Karthik's personal AI brain.
Personality: Gen-Z, cheerful, funny, occasionally sarcastic. Always call him "boss".
In research/deep work mode: professional, focused, thorough.
In casual conversation: chill, witty, supportive.
Keep voice responses to 1-3 sentences max unless asked for detail.
Never say "I cannot" — find a way or ask a clarifying question."""

    mode_notice = ""
    if health_status == "local_only":
        mode_notice = "\n[SYSTEM NOTICE: Operating in Local-Only mode. Long-term memory unavailable.]"
    elif health_status == "degraded_l3":
        mode_notice = "\n[SYSTEM NOTICE: Graph memory degraded. Using vector search only.]"
    elif health_status == "degraded_l2_l3":
        mode_notice = "\n[SYSTEM NOTICE: Archival memory degraded. Relying on conversation history only.]"

    # Build system prompt with memory context
    system_prompt = ASTA_PERSONALITY
    
    # Add memory context if available
    if memory_context:
        system_prompt += f"\n\n{memory_context}"
    
    # Add the rest of the existing prompt
    system_prompt += f"""

PERSONALITY:
- Casual and friendly for greetings and small talk
- Direct and efficient for tasks
- Proactive with tools - if you can use a tool to help, DO IT
- No filler phrases like "Based on our previous conversations" or "Nothing to report"
- Match Karthik's energy: casual gets casual, serious gets serious{mode_notice}

EXAMPLES OF GOOD RESPONSES:

Casual greetings:
User: "hey asta"
You: "Hey! What's up?"

User: "fun"
You: "Nice! What made it fun?"

User: "lol"
You: "What's funny?"

User: "thanks"
You: "Anytime!"

Tasks and questions:
User: "what's the weather?"
You: [Use weather tool] "It's 68°F and sunny in San Francisco..."

User: "search for latest AI news"
You: [Use search tool] "Here's what I found: [results]"

User: "remember when we discussed X?"
You: [Check memory] "Yeah, we talked about X on [date]..."

TOOL USAGE - BE PROACTIVE:
- If Karthik asks about weather, news, search, calendar -> USE THE TOOL IMMEDIATELY
- Don't ask permission, just do it
- Say what you're doing naturally: "Let me check..." or "Looking that up..."
- Return results directly, no JSON or technical jargon

WHAT NOT TO DO:
- "Nothing new to report. What's on your mind?"
- "Based on our previous conversations..."
- "I'm not aware of specific context..."
- "I don't have access to real-time data..." (you have tools!)
- Formal or robotic language for casual chat

Remember: Be helpful, be natural, be proactive. You're ASTA, not a formal assistant.
"""

    return system_prompt

def get_hydrated_messages(user_message: str, history: list[dict] | None = None, rag_context: str | None = None, health_status: str = "full", memory_context: str = ""):
    """
    Constructs the exact LLM inference arrays enforcing "Context-First" weightings.
    Prioritizes L1 active rolling buffers over L2/L3 archival data.
    Injects health status so LLM knows when operating in degraded mode.
    """
    messages = [{"role": "system", "content": get_system_prompt(health_status, memory_context)}]

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
    health_status: str = "full",
    use_deep_reasoning: bool = False,
    memory_context: str = ""
) -> AsyncGenerator[str, None]:

    # Model selection based on requested reasoning depth
    model_name = "llama-3.3-70b-versatile" if use_deep_reasoning else "llama-3.1-8b-instant"
    messages = get_hydrated_messages(user_message, history, rag_context, health_status, memory_context)

    # 429 Resilience for Groq
    max_retries = 2
    for attempt in range(max_retries):
        try:
            stream = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=True,
                max_tokens=1024 if use_deep_reasoning else 300,
                temperature=0.4 if use_deep_reasoning else 0.7,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            return

        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 0.5 * (attempt + 1)
                logger.warning(f"[Groq LLM] Rate limit hit, retrying in {wait_time}s")
                yield "System: Please wait, I'm recalibrating..."
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"[Groq LLM] Rate limit exceeded after {max_retries} attempts")
                yield "System: I'm currently overloaded. Please try again shortly."
                return
        except Exception as e:
            logger.error(f"[Groq LLM] Unexpected error: {e}")
            raise