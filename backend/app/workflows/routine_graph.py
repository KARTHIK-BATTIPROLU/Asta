"""
ASTA Routine Workflow Graph
Handles morning alarm, briefs, tasks, night planning.
"""
import logging
import asyncio
from datetime import datetime, date
from langgraph.graph import StateGraph, START, END

from backend.app.core.state import RoutineState, add_stage
from backend.app.core.llm_router import llm_router
from backend.app.services.notion_service import notion_service
from backend.app.services.weather_service import weather_service
from backend.app.services.research_service import research_service
from backend.app.services.preferences_service import preferences_service

logger = logging.getLogger(__name__)

ASTA_MORNING_SYSTEM = """You are ASTA, Karthik's personal AI assistant. 
Gen-Z, funny, energetic. Always call him "boss". Keep responses under 150 words."""

ASTA_NIGHT_SYSTEM = """You are ASTA doing end-of-day planning with Karthik. 
Be calm, organized, helpful. Keep responses concise. Always call him "boss"."""


# ── NODES ────────────────────────────────────────────────────────────────────

async def detect_routine_phase(state: RoutineState) -> RoutineState:
    """Detect which routine phase to enter based on input and time."""
    user_input = state.get("current_input", "").lower()
    hour = datetime.now().hour
    
    if state.get("routine_phase"):
        return state
    
    if any(w in user_input for w in ["good morning", "wake", "alarm", "morning"]) or hour < 10:
        state["routine_phase"] = "morning_brief"
    elif any(w in user_input for w in ["night", "plan tomorrow", "end of day", "wrap up"]) or hour >= 21:
        state["routine_phase"] = "night_planning"
    elif any(w in user_input for w in ["add", "create", "schedule", "remind", "task", "tasks", "meeting", "meet", "attend", "what's my plan", "routine", "agenda"]):
        state["routine_phase"] = "task_management"
    else:
        state["routine_phase"] = "general"
    
    state["intermediate_stages"] = add_stage(
        state, "routine_phase_detection", "done", state["routine_phase"]
    )
    return state


async def morning_alarm(state: RoutineState) -> RoutineState:
    """Generate morning alarm wake-up message."""
    messages = [
        {"role": "system", "content": ASTA_MORNING_SYSTEM},
        {"role": "user", "content": (
            "Generate a funny, energetic, slightly urgent wake-up message for Karthik. "
            "It is 5:30 AM. He has a morning jog scheduled. Make it feel like a hype "
            "best friend waking him up. Max 2 sentences."
        )}
    ]
    result = await llm_router.invoke("voice_response", messages)
    state["asta_response"] = result.get("content", "Boss! 5:30 already! Time to jog — get UP!")
    state["alarm_acknowledged"] = False
    state["nag_count"] = 0
    state["intermediate_stages"] = add_stage(state, "morning_alarm", "triggered", "")
    return state


async def nag_loop(state: RoutineState) -> RoutineState:
    """Nag user to wake up with increasing urgency."""
    count = state.get("nag_count", 0) + 1
    state["nag_count"] = count
    
    nag_levels = [
        "Boss... still in bed? Come on, 5 more minutes is a lie you tell yourself 😤",
        "OK BOSS. GET. UP. NOW. The jog isn't going to run itself.",
        "I'm literally begging you at this point. WAKE UP. You said 5:30.",
        "That's it. I'm putting this on repeat until you move. GET UP BOSS.",
        "Fine. Last warning. You asked me to nag you and I'm NAGGING YOU."
    ]
    state["asta_response"] = nag_levels[min(count-1, len(nag_levels)-1)]
    state["intermediate_stages"] = add_stage(state, "nag", "active", f"nag count: {count}")
    return state


async def morning_brief(state: RoutineState) -> RoutineState:
    """Generate comprehensive morning brief with weather, news, and tasks."""
    today = date.today().isoformat()
    state["intermediate_stages"] = add_stage(state, "morning_brief", "fetching_data", "")
    
    # Parallel fetch: weather + news + tasks
    weather_task = asyncio.create_task(weather_service.get_weather())
    news_prefs = await preferences_service.get("news")
    news_query = f"{' OR '.join(news_prefs.get('topics', ['tech news'])[:2])} news today"
    news_task = asyncio.create_task(research_service.search(news_query, num_results=8))
    tasks_task = asyncio.create_task(notion_service.get_pending_tasks(today))
    
    weather, news_results, tasks = await asyncio.gather(
        weather_task, news_task, tasks_task, return_exceptions=True
    )
    
    weather_str = weather.get("summary", "Weather unavailable") if isinstance(weather, dict) else "Weather unavailable"
    news_items = news_results[:5] if isinstance(news_results, list) else []
    pending_tasks = tasks if isinstance(tasks, list) else []
    
    state["weather_data"] = weather if isinstance(weather, dict) else {}
    state["news_items"] = news_items
    state["todays_tasks"] = pending_tasks
    
    news_text = "\n".join([
        f"- {n['title']}: {n['snippet'][:80]}" for n in news_items
    ]) or "No news fetched."
    tasks_text = "\n".join([
        f"- {t['task_name']} at {t.get('scheduled_time','')}" for t in pending_tasks
    ]) or "No tasks scheduled."
    
    brief = await llm_router.invoke_with_system(
        "voice_response",
        ASTA_MORNING_SYSTEM,
        f"""Give Karthik an energetic morning brief. Keep it to 100-120 words. 

Weather: {weather_str}
Top news:
{news_text}
Today's tasks:
{tasks_text}

Format: Greeting → weather in 1 line → top 2 news in 1 line each → tasks rundown → motivational closer."""
    )
    
    state["asta_response"] = brief
    state["intermediate_stages"] = add_stage(
        state, "morning_brief", "done", f"{len(news_items)} news, {len(pending_tasks)} tasks"
    )
    return state


async def task_management(state: RoutineState) -> RoutineState:
    """Handle task viewing, creation, and management."""
    user_input = state.get("current_input", "")
    today = date.today().isoformat()
    memory_ctx = state.get("memory_context", "")
    
    # Check if this is a task creation request
    is_adding_task = any(w in user_input.lower() for w in ["add", "create", "schedule", "remind", "attend", "meeting", "meet"])
    
    if is_adding_task:
        # Use LLM to extract task details from user input
        extraction_prompt = f"""Extract task details from this request: "{user_input}"

Return in this format:
Task Name: [clear task description]
Time: [time if mentioned, or "Not specified"]

Be concise and clear."""
        
        extraction = await llm_router.invoke_with_system(
            "quick_response",
            "You are a task extraction assistant. Extract task name and time from user requests.",
            extraction_prompt
        )
        
        # Parse the extraction (simple approach)
        lines = extraction.split("\n")
        task_name = user_input  # Default to full input
        scheduled_time = ""
        
        for line in lines:
            if line.startswith("Task Name:"):
                task_name = line.replace("Task Name:", "").strip()
            elif line.startswith("Time:"):
                time_str = line.replace("Time:", "").strip()
                if time_str.lower() != "not specified":
                    scheduled_time = time_str
        
        # Create the task in Notion
        try:
            page_id = await notion_service.create_routine_task(
                task_name=task_name,
                task_type="Dynamic",
                scheduled_time=scheduled_time,
                date=today
            )
            
            response = await llm_router.invoke_with_system(
                "quick_response",
                ASTA_MORNING_SYSTEM,
                f"Confirm to Karthik that you've added this task to his Notion: '{task_name}' {f'at {scheduled_time}' if scheduled_time else 'for today'}. Be brief and friendly, max 40 words."
            )
            
            state["intermediate_stages"] = add_stage(
                state, "task_management", "task_created", f"Created: {task_name}"
            )
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            response = f"Boss, I tried to add that task but hit an error: {str(e)}"
            state["intermediate_stages"] = add_stage(
                state, "task_management", "error", str(e)
            )
    else:
        # Viewing tasks
        tasks = await notion_service.get_pending_tasks(today)
        tasks_text = "\n".join([
            f"- {t['task_name']} [{t['status']}] {t.get('scheduled_time', '')}" for t in tasks
        ]) or "No tasks today."
        
        response = await llm_router.invoke_with_system(
            "quick_response",
            f"""{ASTA_MORNING_SYSTEM}
Today's tasks:
{tasks_text}
{memory_ctx}""",
            f"Karthik says: {user_input}\n\nList his tasks in a friendly way. Keep response under 80 words."
        )
        
        state["todays_tasks"] = tasks
        state["intermediate_stages"] = add_stage(
            state, "task_management", "tasks_listed", f"{len(tasks)} tasks"
        )
    
    state["asta_response"] = response
    state["is_complete"] = True
    return state


async def night_planning(state: RoutineState) -> RoutineState:
    """Start end-of-day planning session."""
    today = date.today().isoformat()
    state["intermediate_stages"] = add_stage(state, "night_planning", "started", "")
    
    incomplete = [
        t for t in await notion_service.get_pending_tasks(today) 
        if t.get("status") != "Completed"
    ]
    state["pending_tasks"] = incomplete
    
    incomplete_text = "\n".join([
        f"- {t['task_name']}" for t in incomplete
    ]) or "All tasks done! Great day boss."
    
    response = await llm_router.invoke_with_system(
        "voice_response",
        ASTA_NIGHT_SYSTEM,
        f"""It's 10:30 PM. Start the end-of-day planning session.

Incomplete tasks from today:
{incomplete_text}

Ask Karthik: which to reschedule vs drop, and what new tasks to add for tomorrow. Keep it conversational, max 80 words."""
    )
    
    state["asta_response"] = response
    state["intermediate_stages"] = add_stage(
        state, "night_planning", "awaiting_input", f"{len(incomplete)} incomplete"
    )
    return state


async def gratitude_prompt(state: RoutineState) -> RoutineState:
    """Prompt for gratitude journal entry."""
    response = await llm_router.invoke_with_system(
        "voice_response",
        ASTA_NIGHT_SYSTEM,
        "Night planning is wrapping up. Ask Karthik for one thing he's grateful for today. Be warm, genuine. Max 1 sentence."
    )
    state["asta_response"] = response
    state["intermediate_stages"] = add_stage(state, "gratitude_prompt", "awaiting_input", "")
    return state


async def save_gratitude(state: RoutineState) -> RoutineState:
    """Save gratitude entry to Notion."""
    user_input = state.get("current_input", "")
    today = date.today().isoformat()
    
    if user_input and len(user_input) > 3:
        await notion_service.append_to_gratitude_page(user_input, today)
        state["asta_response"] = "Saved boss. 🙏 Rest well — tomorrow we attack."
    else:
        state["asta_response"] = "All good boss. Rest up."
    
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(state, "gratitude_saved", "done", "")
    return state


# ── ROUTING ──────────────────────────────────────────────────────────────────

def route_after_detection(state: RoutineState) -> str:
    """Route to appropriate workflow phase after detection."""
    phase = state.get("routine_phase", "general")
    routing = {
        "morning_alarm": "morning_alarm",
        "morning_brief": "morning_brief",
        "night_planning": "night_planning",
        "task_management": "task_management",
        "general": "task_management",
    }
    return routing.get(phase, "task_management")


def route_alarm(state: RoutineState) -> str:
    """Route after alarm - either to brief or continue nagging."""
    if state.get("alarm_acknowledged") or state.get("nag_count", 0) >= 5:
        return "morning_brief"
    return "nag_loop"


# ── GRAPH ────────────────────────────────────────────────────────────────────

def build_routine_graph():
    """Build and compile the routine workflow graph."""
    graph = StateGraph(RoutineState)
    
    # Add nodes
    graph.add_node("detect_phase", detect_routine_phase)
    graph.add_node("morning_alarm", morning_alarm)
    graph.add_node("nag_loop", nag_loop)
    graph.add_node("morning_brief", morning_brief)
    graph.add_node("task_management", task_management)
    graph.add_node("night_planning", night_planning)
    graph.add_node("gratitude_prompt", gratitude_prompt)
    graph.add_node("save_gratitude", save_gratitude)
    
    # Add edges
    graph.add_edge(START, "detect_phase")
    graph.add_conditional_edges("detect_phase", route_after_detection, {
        "morning_alarm": "morning_alarm",
        "morning_brief": "morning_brief",
        "night_planning": "night_planning",
        "task_management": "task_management",
    })
    graph.add_conditional_edges("morning_alarm", route_alarm, {
        "morning_brief": "morning_brief",
        "nag_loop": "nag_loop",
    })
    graph.add_edge("nag_loop", "morning_alarm")
    graph.add_edge("morning_brief", END)
    graph.add_edge("task_management", END)
    graph.add_edge("night_planning", "gratitude_prompt")
    graph.add_edge("gratitude_prompt", "save_gratitude")
    graph.add_edge("save_gratitude", END)
    
    return graph.compile()


# Global compiled graph
routine_graph = build_routine_graph()
