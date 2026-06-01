"""
ASTA LinkedIn Workflow Graph
Handles LinkedIn post creation with discussion, generation, and publishing.
"""
import logging
import json
from langgraph.graph import StateGraph, START, END

from backend.app.core.state import LinkedInState, add_stage
from backend.app.core.llm_router import llm_router
from backend.app.services.notion_service import notion_service
from backend.app.services.sheets_service import sheets_service
from backend.app.services.image_service import image_service
from backend.app.services.preferences_service import preferences_service
from backend.app.db.async_mongo import get_async_db

logger = logging.getLogger(__name__)

DISCUSSION_SYSTEM = (
    "You are ASTA helping Karthik develop a LinkedIn post idea. "
    "Ask ONE question to extract his unique angle, personal experience, or insight on this topic. "
    "Professional but casual. Max 40 words."
)


# ── NODES ──────────────────────────────────────────────────────────────────

async def load_calendar_topics(state: LinkedInState) -> LinkedInState:
    """Load pending LinkedIn topics from content calendar."""
    db = await get_async_db()
    topics = await db["content_calendar"].find(
        {"platform": "linkedin", "status": "pending"},
        {"_id": 0, "topic": 1}
    ).limit(5).to_list(5)
    state["calendar_topics"] = [t["topic"] for t in topics]
    
    topics_list = "\n".join([
        f"{i+1}. {t}" for i, t in enumerate(state["calendar_topics"])
    ]) or "No calendar topics yet."
    state["asta_response"] = (
        f"LinkedIn time, boss! Got a topic in mind, or pick from your list?\n\n"
        f"{topics_list}\n\nOr say 'surprise me' 🎲"
    )
    state["intermediate_stages"] = add_stage(
        state, "calendar_loaded", "done", f"{len(state['calendar_topics'])} topics"
    )
    return state


def get_topic_from_response(state: LinkedInState) -> str:
    """Route based on topic selection."""
    user_input = state.get("current_input", "").lower()
    calendar = state.get("calendar_topics", [])
    
    if "surprise" in user_input and calendar:
        return "topic_selected_calendar"
    for t in calendar:
        if t.lower() in user_input:
            return "topic_selected_calendar"
    if len(user_input) > 5:
        return "topic_selected_custom"
    return "awaiting_topic"


async def set_topic_from_calendar(state: LinkedInState) -> LinkedInState:
    """Set topic from calendar selection."""
    user_input = state.get("current_input", "").lower()
    calendar = state.get("calendar_topics", [])
    
    matched = next((t for t in calendar if t.lower() in user_input), None)
    if not matched and calendar:
        matched = calendar[0]  # surprise me or first item
    
    state["topic"] = matched or "default topic"
    state["topic_source"] = "calendar"
    state["intermediate_stages"] = add_stage(state, "topic_set", "done", state["topic"])
    return state


async def set_topic_custom(state: LinkedInState) -> LinkedInState:
    """Set custom topic from user input."""
    topic_result = await llm_router.invoke_with_system(
        "intent_classification",
        "Extract the LinkedIn post topic from this message. Return only the topic phrase, max 10 words.",
        state.get("current_input", "")
    )
    state["topic"] = topic_result.strip()
    state["topic_source"] = "custom"
    state["intermediate_stages"] = add_stage(state, "topic_set", "done", state["topic"])
    return state


async def deep_discuss(state: LinkedInState) -> LinkedInState:
    """Conduct deep discussion to extract user's angle."""
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    turn_count = len([m for m in messages if m.get("role") == "user"])
    
    if turn_count <= 1:
        state["asta_response"] = (
            f"Nice! {topic} — what's your personal take on this? "
            f"Any experience or hot take we can build the post around?"
        )
    else:
        convo = "\n".join([
            f"{m['role'].upper()}: {str(m.get('content',''))[:200]}" 
            for m in messages[-4:]
        ])
        q = await llm_router.invoke_with_system(
            "voice_response",
            DISCUSSION_SYSTEM,
            f"Topic: {topic}\nConversation:\n{convo}"
        )
        state["asta_response"] = q
    return state


def check_discussion_ready(state: LinkedInState) -> str:
    """Check if ready to generate post or continue discussion."""
    user_input = state.get("current_input", "").lower()
    messages = state.get("messages", [])
    turn_count = len([m for m in messages if m.get("role") == "user"])
    
    triggers = ["write it", "create the post", "generate", "that's enough", "go ahead", "make it"]
    if any(t in user_input for t in triggers) or turn_count >= 4:
        return "generate_post"
    return "deep_discuss"


async def generate_post_node(state: LinkedInState) -> LinkedInState:
    """Generate LinkedIn post based on preferences and discussion."""
    prefs = await preferences_service.get("linkedin")
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    user_messages = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    discussion = "\n".join(f"- {m[:300]}" for m in user_messages)
    
    state["intermediate_stages"] = add_stage(state, "generating_post", "started", "")
    
    post_result = await llm_router.invoke_with_system(
        "post_generation",
        f"""You are writing a LinkedIn post for Karthik with these preferences:
Tone: {prefs.get('tone','')}
Style: {prefs.get('writing_style','')}
Audience: {prefs.get('audience','')}
Format: {prefs.get('post_format','')}
Avoid: {', '.join(prefs.get('avoid',[]))}

Write a LinkedIn post on this topic that reflects his personal angle from the discussion.
Return ONLY valid JSON: {{"post_body": "...", "hashtags": ["...", ...]}}
Include exactly {prefs.get('hashtag_count', 5)} hashtags.
""",
        f"Topic: {topic}\n\nKarthik's angle from discussion:\n{discussion}"
    )
    
    try:
        raw = post_result.strip().strip("```json").strip("```").strip()
        parsed = json.loads(raw)
        state["post_body"] = parsed.get("post_body", "")
        state["hashtags"] = parsed.get("hashtags", [])
    except:
        state["post_body"] = post_result
        state["hashtags"] = [f"#{topic.replace(' ', '')}", "#LinkedIn", "#Tech"]
    
    state["discussion_summary"] = discussion
    state["preferences_applied"] = prefs
    state["intermediate_stages"] = add_stage(
        state, "post_generated", "done", f"{len(state['post_body'])} chars"
    )
    return state


async def generate_images_node(state: LinkedInState) -> LinkedInState:
    """Generate images for the post."""
    state["intermediate_stages"] = add_stage(state, "generating_images", "started", "")
    images = await image_service.generate_images(
        topic=state.get("topic", ""),
        post_body=state.get("post_body", ""),
        count=4
    )
    state["generated_images"] = images
    state["intermediate_stages"] = add_stage(
        state, "images_generated", "done", f"{len(images)} images"
    )
    return state


async def write_to_sheet(state: LinkedInState) -> LinkedInState:
    """Write post to Google Sheets and log to Notion."""
    hashtag_str = " ".join(state.get("hashtags", []))
    first_image = state.get("generated_images", [{}])[0]
    media_url = first_image.get("data", "") if first_image.get("type") == "base64" else ""
    
    row_id = await sheets_service.add_post_row(
        content=state.get("post_body", ""),
        hashtags=hashtag_str,
        media_url=media_url,
        scheduled_time=state.get("scheduled_time", ""),
        status="Draft"
    )
    state["sheet_row_id"] = str(row_id)
    
    # Log to Notion
    await notion_service.log_content_creation(
        "LinkedIn", state.get("topic", ""), state.get("post_body", "")[:100]
    )
    
    # Mark topic as created in MongoDB
    if state.get("topic_source") == "calendar":
        db = await get_async_db()
        await db["content_calendar"].update_one(
            {"platform": "linkedin", "topic": state.get("topic", "")},
            {"$set": {"status": "created"}}
        )
    
    state["asta_response"] = (
        f"Post is ready boss! ✅\n\n"
        f"Added to your Google Sheet as Draft. Review in AppSheet, "
        f"hit Approve and it goes live automatically.\n\n"
        f"Here's a preview:\n\n{state.get('post_body','')[:300]}..."
    )
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(
        state, "written_to_sheet", "done", f"row: {state['sheet_row_id']}"
    )
    return state


# ── GRAPH ──────────────────────────────────────────────────────────────────

def build_linkedin_graph():
    """Build and compile the LinkedIn workflow graph."""
    graph = StateGraph(LinkedInState)
    
    # Add nodes
    graph.add_node("load_topics", load_calendar_topics)
    graph.add_node("set_topic_calendar", set_topic_from_calendar)
    graph.add_node("set_topic_custom", set_topic_custom)
    graph.add_node("deep_discuss", deep_discuss)
    graph.add_node("generate_post", generate_post_node)
    graph.add_node("generate_images", generate_images_node)
    graph.add_node("write_to_sheet", write_to_sheet)
    
    # Add edges
    graph.add_edge(START, "load_topics")
    graph.add_conditional_edges("load_topics", get_topic_from_response, {
        "topic_selected_calendar": "set_topic_calendar",
        "topic_selected_custom": "set_topic_custom",
        "awaiting_topic": "load_topics",
    })
    graph.add_edge("set_topic_calendar", "deep_discuss")
    graph.add_edge("set_topic_custom", "deep_discuss")
    graph.add_conditional_edges("deep_discuss", check_discussion_ready, {
        "deep_discuss": "deep_discuss",
        "generate_post": "generate_post",
    })
    graph.add_edge("generate_post", "generate_images")
    graph.add_edge("generate_images", "write_to_sheet")
    graph.add_edge("write_to_sheet", END)
    
    return graph.compile()


# Global compiled graph
linkedin_graph = build_linkedin_graph()
