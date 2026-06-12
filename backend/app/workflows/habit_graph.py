"""
ASTA Habit Tracking Workflow Graph
Handles DSA, reading, goals, gratitude, metaverse, and community tracking.
"""
import logging
from langgraph.graph import StateGraph, START, END

from backend.app.core.state import HabitState, add_stage
from backend.app.core.llm_factory import llm_router
from backend.app.services.notion_service import notion_service

logger = logging.getLogger(__name__)


# ── NODES ──────────────────────────────────────────────────────────────────

async def detect_habit_type(state: HabitState) -> HabitState:
    """Detect which habit type from user input."""
    user_input = state.get("current_input", "").lower()
    
    # Classify habit type based on keywords
    if any(w in user_input for w in ["dsa", "leetcode", "coding problem", "algorithm"]):
        state["habit_type"] = "dsa"
    elif any(w in user_input for w in ["book", "reading", "pages", "novel", "studying"]):
        state["habit_type"] = "reading"
    elif any(w in user_input for w in ["metaverse", "vr", "ar", "web3", "xr"]):
        state["habit_type"] = "metaverse"
    elif any(w in user_input for w in ["community", "students", "discord", "members"]):
        state["habit_type"] = "community"
    elif any(w in user_input for w in ["goal", "target", "milestone", "career"]):
        state["habit_type"] = "goals"
    elif any(w in user_input for w in ["grateful", "gratitude", "thankful", "appreciate"]):
        state["habit_type"] = "gratitude"
    else:
        state["habit_type"] = "general"
    
    state["intermediate_stages"] = add_stage(
        state, "habit_detected", "done", state["habit_type"]
    )
    return state


def route_to_handler(state: HabitState) -> str:
    """Route to appropriate habit handler."""
    habit_type = state.get("habit_type", "general")
    handlers = {
        "dsa": "dsa_handler",
        "reading": "reading_handler",
        "metaverse": "metaverse_handler",
        "community": "community_handler",
        "goals": "goals_handler",
        "gratitude": "gratitude_handler",
        "general": "general_handler",
    }
    return handlers.get(habit_type, "general_handler")


async def dsa_handler(state: HabitState) -> HabitState:
    """Handle DSA problem tracking."""
    user_input = state.get("current_input", "")
    
    # Check if problem was solved
    solved = any(w in user_input.lower() for w in ["solved", "done", "completed", "finished"])
    
    if solved:
        # Extract problem name
        problem_result = await llm_router.invoke_with_system(
            "intent_classification",
            "Extract the problem name from this message. Return only the problem name.",
            user_input
        )
        problem_name = problem_result.strip()
        
        # Log to Notion
        await notion_service.append_to_habit_page(
            "dsa", 
            f"Solved: {problem_name}"
        )
        
        state["asta_response"] = f"Let's GO! {problem_name} down. Streak alive. Log it! 🔥"
        state["habit_data"]["problem_solved"] = True
        state["habit_data"]["problem_name"] = problem_name
    else:
        state["asta_response"] = "Boss. ONE problem. You've done harder things. Open LeetCode. Now."
        state["habit_data"]["problem_solved"] = False
    
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "dsa_logged", "done", "")
    return state


async def reading_handler(state: HabitState) -> HabitState:
    """Handle reading progress tracking."""
    user_input = state.get("current_input", "")
    
    # Extract reading info
    reading_info = await llm_router.invoke_with_system(
        "intent_classification",
        "Extract book name and pages read (if mentioned). Return format: 'Book: X, Pages: Y' or just 'Book: X'",
        user_input
    )
    
    # Log to Notion
    await notion_service.append_to_habit_page("reading", reading_info.strip())
    
    state["asta_response"] = "Logged boss! 📚 10 pages tonight? Literally 15 minutes."
    state["habit_data"]["reading_logged"] = True
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "reading_logged", "done", "")
    return state


async def metaverse_handler(state: HabitState) -> HabitState:
    """Handle metaverse knowledge tracking."""
    user_input = state.get("current_input", "")
    messages = state.get("messages", [])
    
    # Extract key insights from conversation
    convo = "\n".join([
        str(m.get("content", ""))[:300] 
        for m in messages[-5:] if m.get("role") == "user"
    ])
    
    insights_result = await llm_router.invoke_with_system(
        "intent_classification",
        "Extract 2-3 key insights about metaverse/VR/AR/Web3 from this conversation. "
        "Return as bullet points, one per line.",
        convo
    )
    
    insights = [i.strip().lstrip("-•").strip() for i in insights_result.split("\n") if i.strip()]
    
    # Log each insight to Notion
    for insight in insights:
        await notion_service.append_to_habit_page("metaverse", insight)
    
    state["asta_response"] = f"Got it boss. Added {len(insights)} metaverse insights to your knowledge base. 🌐"
    state["habit_data"]["insights_count"] = len(insights)
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "metaverse_logged", "done", f"{len(insights)} insights")
    return state


async def community_handler(state: HabitState) -> HabitState:
    """Handle community updates tracking."""
    user_input = state.get("current_input", "")
    
    # Log community update
    await notion_service.append_to_habit_page("community", user_input)
    
    state["asta_response"] = "Community update logged boss! Keep building. 🚀"
    state["habit_data"]["community_logged"] = True
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "community_logged", "done", "")
    return state


async def goals_handler(state: HabitState) -> HabitState:
    """Handle professional goals tracking."""
    user_input = state.get("current_input", "")
    
    # Extract goal info
    goal_info = await llm_router.invoke_with_system(
        "intent_classification",
        "Extract the goal or milestone from this message. Be concise.",
        user_input
    )
    
    # Log to Notion
    await notion_service.append_to_habit_page("goals", goal_info.strip())
    
    state["asta_response"] = "Goal logged boss! Let's check your goals real quick — where are you at? 🎯"
    state["habit_data"]["goal_logged"] = True
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "goal_logged", "done", "")
    return state


async def gratitude_handler(state: HabitState) -> HabitState:
    """Handle gratitude journal entries."""
    user_input = state.get("current_input", "")
    
    # Log gratitude entry
    await notion_service.append_to_habit_page("gratitude", user_input)
    
    state["asta_response"] = "Gratitude logged boss. 🙏 Keep that mindset."
    state["habit_data"]["gratitude_logged"] = True
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "gratitude_logged", "done", "")
    return state


async def general_handler(state: HabitState) -> HabitState:
    """Handle general habit tracking."""
    user_input = state.get("current_input", "")
    
    # Ask what to track
    response = await llm_router.invoke_with_system(
        "voice_response",
        "You are ASTA helping Karthik track a habit. Ask what specific habit or progress "
        "he wants to log. Be brief and direct. Max 30 words.",
        f"User said: {user_input}"
    )
    
    state["asta_response"] = response
    state["is_complete"] = False
    state["intermediate_stages"] = add_stage(state, "general_habit", "awaiting_input", "")
    return state


# ── GRAPH ──────────────────────────────────────────────────────────────────

def build_habit_graph():
    """Build and compile the habit tracking workflow graph."""
    graph = StateGraph(HabitState)
    
    # Add nodes
    graph.add_node("detect_habit_type", detect_habit_type)
    graph.add_node("dsa_handler", dsa_handler)
    graph.add_node("reading_handler", reading_handler)
    graph.add_node("metaverse_handler", metaverse_handler)
    graph.add_node("community_handler", community_handler)
    graph.add_node("goals_handler", goals_handler)
    graph.add_node("gratitude_handler", gratitude_handler)
    graph.add_node("general_handler", general_handler)
    
    # Add edges
    graph.add_edge(START, "detect_habit_type")
    graph.add_conditional_edges("detect_habit_type", route_to_handler, {
        "dsa_handler": "dsa_handler",
        "reading_handler": "reading_handler",
        "metaverse_handler": "metaverse_handler",
        "community_handler": "community_handler",
        "goals_handler": "goals_handler",
        "gratitude_handler": "gratitude_handler",
        "general_handler": "general_handler",
    })
    graph.add_edge("dsa_handler", END)
    graph.add_edge("reading_handler", END)
    graph.add_edge("metaverse_handler", END)
    graph.add_edge("community_handler", END)
    graph.add_edge("goals_handler", END)
    graph.add_edge("gratitude_handler", END)
    graph.add_edge("general_handler", END)
    
    return graph.compile()


# Global compiled graph
habit_graph = build_habit_graph()
