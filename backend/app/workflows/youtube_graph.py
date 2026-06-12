"""
ASTA YouTube Workflow Graph
Handles YouTube video script creation with research and formatting.
"""
import logging
from langgraph.graph import StateGraph, START, END

from backend.app.core.state import ContentState, add_stage
from backend.app.core.llm_factory import llm_router
from backend.app.services.research_service import research_service
from backend.app.services.notion_service import notion_service
from backend.app.services.preferences_service import preferences_service
from backend.app.db.async_mongo import get_async_db

logger = logging.getLogger(__name__)

SCRIPT_FORMAT = """
HOOK (0:00-0:30): Most interesting fact/question about topic. Stop the scroll.
STORY/CONTEXT (0:30-2:00): Why this matters. Relatable setup.
DEEP CONTENT (2:00-8:00): Core value. 3-4 main points with examples.
TAKEAWAYS (8:00-9:00): 3 bullet points the viewer walks away with.
CTA (9:00-9:30): Subscribe + tease next video.

For each section include:
- Script text (word for word)
- B-roll suggestions [in brackets]
- On-screen text suggestions {in curly braces}
"""


# ── NODES ──────────────────────────────────────────────────────────────────

async def load_yt_topics(state: ContentState) -> ContentState:
    """Load pending YouTube topics from content calendar."""
    db = await get_async_db()
    topics = await db["content_calendar"].find(
        {"platform": "youtube", "status": "pending"}, 
        {"topic": 1}
    ).limit(5).to_list(5)
    topic_list = [t["topic"] for t in topics]
    topic_str = "\n".join([
        f"{i+1}. {t}" for i, t in enumerate(topic_list)
    ]) or "No topics yet — what's your idea?"
    state["metadata"] = {"calendar_topics": topic_list}
    state["platform"] = "youtube"
    state["asta_response"] = (
        f"YouTube mode boss! Got a topic or pick from your list?\n\n{topic_str}"
    )
    return state


async def set_yt_topic(state: ContentState) -> ContentState:
    """Set YouTube topic from calendar or custom input."""
    user_input = state.get("current_input", "")
    calendar = state.get("metadata", {}).get("calendar_topics", [])
    matched = next((t for t in calendar if t.lower() in user_input.lower()), None)
    if matched:
        state["topic"] = matched
        state["topic_source"] = "calendar"
    else:
        topic = await llm_router.invoke_with_system(
            "intent_classification",
            "Extract the YouTube video topic. Return only the topic, max 10 words.",
            user_input
        )
        state["topic"] = topic.strip()
        state["topic_source"] = "custom"
    state["intermediate_stages"] = add_stage(state, "yt_topic_set", "done", state["topic"])
    return state


async def discuss_yt_topic(state: ContentState) -> ContentState:
    """Discuss video angle and style with user."""
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    convo = "\n".join([
        f"{m['role'].upper()}: {str(m.get('content',''))[:200]}" 
        for m in messages[-4:]
    ])
    turn_count = len([m for m in messages if m.get("role") == "user"])
    
    if turn_count <= 1:
        state["asta_response"] = (
            f"Good choice — {topic}. What's your angle on this? "
            f"Personal experience, or pure educational? And what do you want "
            f"viewers to walk away feeling?"
        )
    else:
        q = await llm_router.invoke_with_system(
            "voice_response",
            "You are ASTA helping Karthik plan a YouTube video. Ask ONE question "
            "about his angle, style, or target audience for this video. Max 30 words.",
            f"Topic: {topic}\n{convo}"
        )
        state["asta_response"] = q
    return state


def check_yt_ready(state: ContentState) -> str:
    """Check if ready to start research or continue discussion."""
    user_input = state.get("current_input", "").lower()
    messages = state.get("messages", [])
    turn_count = len([m for m in messages if m.get("role") == "user"])
    triggers = [
        "research", "write script", "create", "go ahead", "start", "enough", "make it"
    ]
    if any(t in user_input for t in triggers) or turn_count >= 3:
        return "research"
    return "discuss"


async def research_yt_topic(state: ContentState) -> ContentState:
    """Research the topic for script content."""
    topic = state.get("topic", "")
    state["intermediate_stages"] = add_stage(state, "yt_research", "started", "")
    
    research = await research_service.deep_research(topic)
    arxiv = await research_service.search_arxiv(topic)
    
    sources_text = "\n".join([
        f"[{s.get('url','')}] {s.get('content','')[:800]}" 
        for s in research.get("sources", [])[:5]
    ])
    arxiv_text = "\n".join([
        f"- {p['title']}: {p['summary'][:200]}" for p in arxiv[:3]
    ])
    
    state["research_points"] = [
        s.get("title", "") + ": " + s.get("content", "")[:200] 
        for s in research.get("sources", [])[:6]
    ]
    state["metadata"]["sources_text"] = sources_text
    state["metadata"]["arxiv_text"] = arxiv_text
    state["intermediate_stages"] = add_stage(
        state, "yt_research", "done", f"{research.get('total_sources',0)} sources"
    )
    return state


async def generate_yt_script(state: ContentState) -> ContentState:
    """Generate YouTube script with formatting."""
    prefs = await preferences_service.get("youtube")
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    user_msgs = "\n".join([
        str(m.get("content", ""))[:200] 
        for m in messages if m.get("role") == "user"
    ])
    sources = state.get("metadata", {}).get("sources_text", "")
    
    state["intermediate_stages"] = add_stage(state, "script_generation", "started", "")
    
    script = await llm_router.invoke_with_system(
        "script_generation",
        f"""You are ASTA writing a YouTube script for Karthik.
Channel style: {prefs.get('style','')}
Energy: {prefs.get('energy_level','')}
Target length: {prefs.get('target_length_minutes',10)} minutes
Format: {SCRIPT_FORMAT}

Research sources:
{sources[:3000]}""",
        f"Topic: {topic}\nKarthik's angle:\n{user_msgs}\n\nWrite the complete script."
    )
    
    title_ideas = await llm_router.invoke_with_system(
        "quick_response",
        "Generate 3 YouTube video title options. Clickable but honest. One per line.",
        f"Topic: {topic} Script preview: {script[:300]}"
    )
    
    state["script_or_caption"] = script
    state["metadata"]["title_ideas"] = [
        t.strip() for t in title_ideas.strip().split("\n") if t.strip()
    ][:3]
    state["metadata"]["tags"] = [topic] + [
        r.split(":")[0][:20] for r in state.get("research_points", [])[:5]
    ]
    state["intermediate_stages"] = add_stage(
        state, "script_done", "done", f"{len(script)} chars"
    )
    return state


async def save_yt_to_notion(state: ContentState) -> ContentState:
    """Save YouTube script to Notion."""
    page_id = await notion_service.create_youtube_page(
        topic=state.get("topic", ""),
        script=state.get("script_or_caption", ""),
        research_points=state.get("research_points", []),
        metadata=state.get("metadata", {})
    )
    state["notion_page_id"] = page_id
    await notion_service.log_content_creation(
        "YouTube", 
        state.get("topic", ""), 
        state.get("script_or_caption", "")[:100]
    )
    
    if state.get("topic_source") == "calendar":
        db = await get_async_db()
        await db["content_calendar"].update_one(
            {"platform": "youtube", "topic": state.get("topic", "")},
            {"$set": {"status": "created"}}
        )
    
    state["asta_response"] = (
        f"YouTube script done boss! 🎬 Saved to Notion with full research.\n\n"
        f"Title ideas:\n" + "\n".join(state.get("metadata", {}).get("title_ideas", []))
    )
    state["is_complete"] = True
    return state


# ── GRAPH ──────────────────────────────────────────────────────────────────

def build_youtube_graph():
    """Build and compile the YouTube workflow graph."""
    graph = StateGraph(ContentState)
    
    # Add nodes
    graph.add_node("load_topics", load_yt_topics)
    graph.add_node("set_topic", set_yt_topic)
    graph.add_node("discuss", discuss_yt_topic)
    graph.add_node("research", research_yt_topic)
    graph.add_node("generate_script", generate_yt_script)
    graph.add_node("save_to_notion", save_yt_to_notion)
    
    # Add edges
    graph.add_edge(START, "load_topics")
    graph.add_edge("load_topics", "set_topic")
    graph.add_edge("set_topic", "discuss")
    graph.add_conditional_edges("discuss", check_yt_ready, {
        "discuss": "discuss",
        "research": "research"
    })
    graph.add_edge("research", "generate_script")
    graph.add_edge("generate_script", "save_to_notion")
    graph.add_edge("save_to_notion", END)
    
    return graph.compile()


# Global compiled graph
youtube_graph = build_youtube_graph()
