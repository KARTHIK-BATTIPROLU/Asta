import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ToolForcing")

def check_tool_forcing(transcript: str, intent: dict, forced_tool: str, should_use_workflow: bool) -> Optional[Dict[str, Any]]:
    """
    Checks if the user's intent is a direct tool invocation (e.g. weather, search, news, calendar).
    Returns a tool_payload dict if a fast-path tool should be executed, otherwise None.
    """
    if not forced_tool or intent.get('type') != 'tool' or should_use_workflow:
        return None

    logger.info(f"[INTENT] Forcing tool call: {forced_tool}")
    tool_payload = None

    if forced_tool == "weather":
        city = "San Francisco"
        words = transcript.split()
        for i, word in enumerate(words):
            if word.lower() in ["in", "at", "for"] and i + 1 < len(words):
                city = " ".join(words[i+1:])
                break
        
        tool_payload = {
            "action": "api_tool",
            "tool": "weather",
            "operation": "get_current",
            "city": city,
            "intent": f"Get weather for {city}",
            "memory_tag": "weather_query"
        }

    elif forced_tool == "search":
        query = transcript
        for prefix in ["search for", "search", "google", "find", "look up", "what is", "who is", "tell me about"]:
            if query.lower().startswith(prefix):
                query = query[len(prefix):].strip()
                break
        
        tool_payload = {
            "action": "api_tool",
            "tool": "search",
            "operation": "search",
            "query": query,
            "num_results": 5,
            "intent": f"Search for: {query}",
            "memory_tag": "search_query"
        }

    elif forced_tool == "news":
        topic = "general"
        words = transcript.lower().split()
        if "about" in words:
            idx = words.index("about")
            if idx + 1 < len(words):
                topic = " ".join(words[idx+1:])
        
        tool_payload = {
            "action": "api_tool",
            "tool": "news",
            "operation": "get_topic" if topic != "general" else "get_digest",
            "topic": topic,
            "topics": [topic] if topic != "general" else ["technology", "business"],
            "intent": f"Get news about {topic}",
            "memory_tag": "news_query"
        }

    elif forced_tool == "calendar":
        tool_payload = {
            "action": "api_tool",
            "tool": "calendar",
            "operation": "get_today",
            "intent": "Check calendar",
            "memory_tag": "calendar_query"
        }

    elif forced_tool == "study_planner":
        tool_payload = {
            "action": "workflow",
            "tool": "study_planner",
            "intent": "Study planner flow",
            "memory_tag": "study_planner"
        }

    return tool_payload
