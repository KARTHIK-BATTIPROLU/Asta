"""
ASTA Instagram Workflow Graph
Handles Instagram carousel creation with 7-slide structure.
"""
import logging
import json
from langgraph.graph import StateGraph, START, END

from backend.app.core.state import ContentState, add_stage
from backend.app.core.llm_factory import llm_router
from backend.app.services.research_service import research_service
from backend.app.services.notion_service import notion_service
from backend.app.services.preferences_service import preferences_service
from backend.app.db.database import db_manager

logger = logging.getLogger(__name__)

SLIDE_SYSTEM = """
Create a 7-slide Instagram carousel for a tech/productivity audience.

Slide 1 (HOOK): Bold statement or surprising fact. Max 8 words.
Slide 2 (PROBLEM): What problem this solves. Relatable. Max 15 words.
Slide 3-5 (INSIGHTS): One key insight per slide. Simple, visual. Max 20 words each.
Slide 6 (ACTION): One clear action step. Concrete. Max 15 words.
Slide 7 (CTA): Follow for more. Save this. Share. Max 10 words.

Return JSON: {
  "caption": "hook line + 2-3 lines + CTA + hashtags",
  "slides": ["slide 1 text", "slide 2 text", ...7 slides],
  "hashtags": ["tag1", ...25 tags]
}
"""


# ── NODES ──────────────────────────────────────────────────────────────────

async def load_ig_topics(state: ContentState) -> ContentState:
    """Load pending Instagram topics from content calendar."""
    db = db_manager.db
    topics = await db["content_calendar"].find(
        {"platform": "instagram", "status": "pending"}, 
        {"topic": 1}
    ).limit(5).to_list(5)
    topic_list = [t["topic"] for t in topics]
    topic_str = "\n".join([
        f"{i+1}. {t}" for i, t in enumerate(topic_list)
    ]) or "No topics yet — what's your idea?"
    state["metadata"] = {"calendar_topics": topic_list}
    state["platform"] = "instagram"
    state["asta_response"] = (
        f"Instagram carousel time boss! Got a topic or pick from your list?\n\n{topic_str}"
    )
    return state


async def set_ig_topic(state: ContentState) -> ContentState:
    """Set Instagram topic from calendar or custom input."""
    user_input = state.get("current_input", "")
    calendar = state.get("metadata", {}).get("calendar_topics", [])
    matched = next((t for t in calendar if t.lower() in user_input.lower()), None)
    if matched:
        state["topic"] = matched
        state["topic_source"] = "calendar"
    else:
        topic = await llm_router.invoke_with_system(
            "intent_classification",
            "Extract the Instagram carousel topic. Return only the topic, max 10 words.",
            user_input
        )
        state["topic"] = topic.strip()
        state["topic_source"] = "custom"
    state["intermediate_stages"] = add_stage(state, "ig_topic_set", "done", state["topic"])
    return state


async def discuss_ig_topic(state: ContentState) -> ContentState:
    """Discuss carousel angle with user."""
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    convo = "\n".join([
        f"{m['role'].upper()}: {str(m.get('content',''))[:200]}" 
        for m in messages[-4:]
    ])
    turn_count = len([m for m in messages if m.get("role") == "user"])
    
    if turn_count <= 1:
        state["asta_response"] = (
            f"Cool — {topic}. What's the main insight or problem you want to solve? "
            f"Instagram carousels work best when they're super actionable."
        )
    else:
        q = await llm_router.invoke_with_system(
            "voice_response",
            "You are ASTA helping Karthik plan an Instagram carousel. Ask ONE question "
            "about the key insight or action step. Max 30 words.",
            f"Topic: {topic}\n{convo}"
        )
        state["asta_response"] = q
    return state


def check_ig_ready(state: ContentState) -> str:
    """Check if ready to generate content or continue discussion."""
    user_input = state.get("current_input", "").lower()
    messages = state.get("messages", [])
    turn_count = len([m for m in messages if m.get("role") == "user"])
    triggers = [
        "create", "generate", "make it", "go ahead", "start", "enough", "write"
    ]
    if any(t in user_input for t in triggers) or turn_count >= 3:
        return "research"
    return "discuss"


async def research_ig_topic(state: ContentState) -> ContentState:
    """Research the topic if needed."""
    topic = state.get("topic", "")
    state["intermediate_stages"] = add_stage(state, "ig_research", "started", "")
    
    # Light research for Instagram
    research = await research_service.deep_research(topic)
    
    state["research_points"] = [
        s.get("title", "") + ": " + s.get("content", "")[:150] 
        for s in research.get("sources", [])[:4]
    ]
    state["metadata"]["sources_text"] = "\n".join([
        f"{s.get('title','')}: {s.get('snippet','')}" 
        for s in research.get("sources", [])[:3]
    ])
    state["intermediate_stages"] = add_stage(
        state, "ig_research", "done", f"{research.get('total_sources',0)} sources"
    )
    return state


async def generate_ig_content(state: ContentState) -> ContentState:
    """Generate Instagram carousel content."""
    prefs = await preferences_service.get("instagram")
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    user_msgs = "\n".join([
        str(m.get("content", ""))[:200] 
        for m in messages if m.get("role") == "user"
    ])
    sources = state.get("metadata", {}).get("sources_text", "")
    
    state["intermediate_stages"] = add_stage(state, "ig_generation", "started", "")
    
    content_result = await llm_router.invoke_with_system(
        "content_generation",
        f"""You are ASTA creating an Instagram carousel for Karthik.
Style: {prefs.get('caption_style','')}
Niche: {prefs.get('niche','')}
Visual style: {prefs.get('visual_style','')}
Slide count: 7
{SLIDE_SYSTEM}

Research context:
{sources[:1500]}""",
        f"Topic: {topic}\nKarthik's angle:\n{user_msgs}\n\nGenerate the carousel."
    )
    
    try:
        raw = content_result.strip().strip("```json").strip("```").strip()
        parsed = json.loads(raw)
        state["script_or_caption"] = parsed.get("caption", "")
        state["slides"] = parsed.get("slides", [])
        state["hashtags"] = parsed.get("hashtags", [])[:25]
    except:
        # Fallback if JSON parsing fails
        state["script_or_caption"] = content_result[:300]
        state["slides"] = [
            "Hook slide", "Problem slide", "Insight 1", 
            "Insight 2", "Insight 3", "Action slide", "CTA slide"
        ]
        state["hashtags"] = [f"#{topic.replace(' ', '')}", "#Tech", "#Productivity"]
    
    state["intermediate_stages"] = add_stage(
        state, "ig_content_done", "done", f"{len(state['slides'])} slides"
    )
    return state


async def save_ig_to_notion(state: ContentState) -> ContentState:
    """Save Instagram carousel to Notion."""
    page_id = await notion_service.create_instagram_page(
        topic=state.get("topic", ""),
        caption=state.get("script_or_caption", ""),
        hashtags=state.get("hashtags", []),
        slides=state.get("slides", [])
    )
    state["notion_page_id"] = page_id
    await notion_service.log_content_creation(
        "Instagram", 
        state.get("topic", ""), 
        state.get("script_or_caption", "")[:100]
    )
    
    if state.get("topic_source") == "calendar":
        db = db_manager.db
        await db["content_calendar"].update_one(
            {"platform": "instagram", "topic": state.get("topic", "")},
            {"$set": {"status": "created"}}
        )
    
    slides_preview = "\n".join([
        f"Slide {i+1}: {s[:50]}..." 
        for i, s in enumerate(state.get("slides", [])[:3])
    ])
    state["asta_response"] = (
        f"Instagram carousel ready boss! 📱 Saved to Notion.\n\n"
        f"Preview:\n{slides_preview}\n\n"
        f"Caption: {state.get('script_or_caption','')[:100]}..."
    )
    state["is_complete"] = True
    return state


# ── GRAPH ──────────────────────────────────────────────────────────────────

def build_instagram_graph():
    """Build and compile the Instagram workflow graph."""
    graph = StateGraph(ContentState)
    
    # Add nodes
    graph.add_node("load_topics", load_ig_topics)
    graph.add_node("set_topic", set_ig_topic)
    graph.add_node("discuss", discuss_ig_topic)
    graph.add_node("research", research_ig_topic)
    graph.add_node("generate_content", generate_ig_content)
    graph.add_node("save_to_notion", save_ig_to_notion)
    
    # Add edges
    graph.add_edge(START, "load_topics")
    graph.add_edge("load_topics", "set_topic")
    graph.add_edge("set_topic", "discuss")
    graph.add_conditional_edges("discuss", check_ig_ready, {
        "discuss": "discuss",
        "research": "research"
    })
    graph.add_edge("research", "generate_content")
    graph.add_edge("generate_content", "save_to_notion")
    graph.add_edge("save_to_notion", END)
    
    return graph.compile()


# Global compiled graph
instagram_graph = build_instagram_graph()
