import asyncio
import json
import logging
from typing import List, Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from backend.app.config import config
from backend.app.models.session_model import SessionSummary

logger = logging.getLogger(__name__)

_llm_summarizer = None

def _get_llm_summarizer():
    global _llm_summarizer
    if _llm_summarizer is None:
        _llm_summarizer = ChatGroq(
            model_name=config.MODEL_NAME or "llama-3.3-70b-versatile",
            temperature=0.3,
            groq_api_key=config.GROQ_API_KEY
        )
    return _llm_summarizer

SUMMARY_SYSTEM_PROMPT = """
You are an expert AI session analyzer.
Your task is to analyze a conversation reset between a user and an AI assistant.
You must extract:
1. A concise summary of the conversation (what was discussed, decisions made).
2. Key topics/keywords (as a list of strings).
3. Context tags (e.g., "development", "personal", "health", "finance").

Output MUST be a valid JSON object with the following structure:
{
  "summary": "The user asked about...",
  "keywords": ["keyword1", "keyword2"],
  "context_tags": ["tag1", "tag2"]
}
Do NOT include any text outside the JSON object.
"""


def _fallback_summary(messages: List[Dict[str, Any]]) -> SessionSummary:
    user_msgs = [m.get("content", "").strip() for m in messages if m.get("role") == "user" and m.get("content")]
    assistant_msgs = [m.get("content", "").strip() for m in messages if m.get("role") == "assistant" and m.get("content")]

    summary_parts = []
    if user_msgs:
        summary_parts.append(f"User discussed {len(user_msgs)} message(s)")
        summary_parts.append(f"first topic: {user_msgs[0][:120]}")
    if assistant_msgs:
        summary_parts.append(f"assistant replied {len(assistant_msgs)} time(s)")

    summary_text = ". ".join(summary_parts).strip()
    if not summary_text:
        summary_text = f"Session with {len(messages)} message(s) was completed."

    keywords = []
    for text in user_msgs[:4]:
        keywords.extend([w.lower() for w in text.split() if len(w) > 4][:3])

    return SessionSummary(
        summary=summary_text,
        keywords=list(dict.fromkeys(keywords))[:8],
        context_tags=["chat", "fallback-summary"],
    )


def _extract_json_block(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned

async def generate_session_summary(messages: List[Dict[str, Any]]) -> SessionSummary:
    """
    Generates a summary, keywords, and context tags from a list of messages.
    """
    if not messages:
        return SessionSummary(
            summary="Empty session",
            keywords=[],
            context_tags=[]
        )

    # Format conversation history
    conversation_text = ""
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        conversation_text += f"{role}: {content}\n"

    # Truncate to prevent LLM context overflow (approx. 3000 tokens)
    MAX_CONVERSATION_CHARS = 12000
    if len(conversation_text) > MAX_CONVERSATION_CHARS:
        logger.warning(f"Truncating conversation history from {len(conversation_text)} to {MAX_CONVERSATION_CHARS} chars.")
        conversation_text = "...[truncated]...\n" + conversation_text[-MAX_CONVERSATION_CHARS:]

    try:
        response = await asyncio.wait_for(_get_llm_summarizer().ainvoke([
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze this conversation:\n\n{conversation_text}")
        ]), timeout=config.AGENT_TIMEOUT_SECONDS)
        
        content = _extract_json_block(response.content)
        
        try:
            data = json.loads(content)
            summary = SessionSummary(**data)
            if not summary.summary.strip():
                logger.warning("Summary empty from LLM; using fallback summary")
                return _fallback_summary(messages)
            return summary
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON summary from LLM: {content}")
            return _fallback_summary(messages)
    except asyncio.TimeoutError:
        logger.error("Session summary generation timed out")
        return _fallback_summary(messages)
            
    except Exception as e:
        logger.error(f"Error generating session summary: {e}")
        return _fallback_summary(messages)
