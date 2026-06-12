"""
ASTA Supervisor — real LangGraph StateGraph.

Flow:  START → classify_intent → (route) → [routine_workflow | other_workflow] → save_session → END

The supervisor classifies intent, routes to a workflow, then persists the turn
to MongoDB. Compiled with a checkpointer so every step is checkpointed per
session (thread_id = session_id).
"""
import logging
from datetime import datetime, date
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from backend.app.core.llm_factory import acomplete
from backend.app.core.checkpointer import get_checkpointer

logger = logging.getLogger("SupervisorGraph")

VALID_INTENTS = ("routine", "research", "content", "linkedin", "other")

CHAT_SYSTEM = (
    "You are ASTA, Kartik's personal AI assistant. Warm, sharp, concise. "
    "Call him 'boss'. Reply in natural language, never JSON. Max 80 words."
)


# ── STATE ────────────────────────────────────────────────────────────────────

class SupervisorState(TypedDict, total=False):
    user_input: str
    intent: str
    task_data: dict
    response: str
    session_id: str
    messages: list
    memory_context: str
    start_time: str
    error: str
    research_context: dict
    content_state: dict


# Keep references to fire-and-forget memory writes so they aren't GC'd mid-flight.
_bg_tasks: set = set()


def _fire(coro):
    """Run a coroutine in the background without blocking the turn."""
    import asyncio
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


# ── NODES ────────────────────────────────────────────────────────────────────

async def classify_intent(state: SupervisorState) -> SupervisorState:
    """Classify the user input into routine / research / linkedin / other."""
    text = (state.get("user_input") or "").strip()

    # If content_workflow is awaiting review feedback on a draft from the
    # previous turn, this message is the answer to that — route straight back
    # regardless of keywords (see content_manager.py for why this isn't a
    # second interrupt()).
    if (state.get("content_state") or {}).get("phase") == "awaiting_review":
        state["intent"] = "content"
        return state

    # Fast keyword path for the routine vertical (cheap + reliable).
    low = text.lower()
    routine_kw = ["remind", "remimder", "reminder", "schedule", "task", "tasks", "add a",
                  "morning", "night", "wake", "alarm", "plan my day", "to-do", "todo",
                  # task management: list / complete / reschedule
                  "my list", "my plan", "my day", "what's on", "whats on", "agenda",
                  "what do i have", "mark ", "done", "complete", "finished",
                  "move the", "move my", "reschedule", "postpone", "push the"]
    if any(k in low for k in routine_kw):
        state["intent"] = "routine"
        return state

    # Fast keyword path for content creation (LinkedIn/YouTube/Instagram posts
    # and scripts), including the "remember this for my posts" pref-update phrase.
    content_kw = ["linkedin", "instagram", "youtube", "carousel", "reel script", "video script",
                  "write a post", "write a script", "make me a post", "make a post", "create a post",
                  "draft a post", "post about", "content for", "caption for",
                  "remember this for my post", "remember this for my content"]
    if any(k in low for k in content_kw):
        state["intent"] = "content"
        return state

    try:
        raw = await acomplete(
            system=(
                "Classify the user's message into exactly one label: "
                "routine, research, content, or other. "
                "routine = reminders/tasks/scheduling/daily planning. "
                "research = deep research / web lookup. "
                "content = social media content creation (LinkedIn post, YouTube script, Instagram caption). "
                "other = anything else. Reply with ONLY the label."
            ),
            user=text,
            task="classify",
            temperature=0.0,
            max_tokens=8,
        )
        label = (raw or "").strip().lower().split()[0] if raw else "other"
        state["intent"] = label if label in VALID_INTENTS else "other"
    except Exception as e:
        logger.error(f"[classify_intent] {e}")
        state["intent"] = "other"
        state["error"] = str(e)

    logger.info(f"[classify_intent] '{text[:40]}' → {state['intent']}")
    return state


def route_to_workflow(state: SupervisorState) -> str:
    """Conditional edge: route by classified intent."""
    intent = state.get("intent")
    if intent == "routine":
        return "routine_workflow"
    if intent == "research":
        return "research_workflow"
    if intent in ("content", "linkedin"):
        return "content_workflow"
    return "other_workflow"


# Greetings/alarms/end-of-day stay on the existing routine_graph (also driven by
# the scheduler). Everything else is conversational task management.
_MORNING_NIGHT_KW = ["good morning", "wake me", "wake up", "alarm", "morning brief",
                     "night planning", "plan tomorrow", "plan for tomorrow",
                     "end of day", "wrap up", "good night", "gratitude"]


async def routine_workflow(state: SupervisorState) -> SupervisorState:
    """Route routine input: conversational task CRUD, or the morning/night graph."""
    user_input = state.get("user_input", "")
    low = user_input.lower()

    # Conversational task management (create/list/complete/reschedule) — runs in
    # this checkpointed node so interrupt() can pause/resume on the thread_id.
    if not any(w in low for w in _MORNING_NIGHT_KW):
        from backend.app.workflows.task_manager import handle_routine_turn
        from langgraph.errors import GraphInterrupt
        try:
            result = await handle_routine_turn(user_input)
        except GraphInterrupt:
            raise  # must propagate so the graph pauses for clarification
        except Exception as e:
            logger.error(f"[routine_workflow:task] {e}", exc_info=True)
            state["response"] = f"Boss, I hit a snag with that task: {e}"
            state["error"] = str(e)
            return state
        state["response"] = result.get("response", "Done, boss.")
        state["task_data"] = result.get("task_data", {}) or {}
        if result.get("notion_page_id"):
            state["task_data"]["notion_page_id"] = result["notion_page_id"]
        return state

    # Morning brief / night planning / alarm → existing routine graph (unchanged).
    try:
        from backend.app.workflows.routine_graph import routine_graph

        routine_state = {
            "session_id": state.get("session_id", ""),
            "workflow_type": "routine",
            "messages": state.get("messages", []),
            "current_input": state.get("user_input", ""),
            "asta_response": "",
            "memory_context": "",
            "retrieved_memories": [],
            "session_summary": "",
            "needs_clarification": False,
            "clarification_question": "",
            "is_complete": False,
            "notion_page_id": None,
            "tools_used": [],
            "intermediate_stages": [],
            "error": None,
            "start_time": datetime.utcnow().isoformat(),
            "pending_tasks": [],
            "todays_tasks": [],
            "task_data": {},
            "weather_data": {},
            "news_items": [],
            "gratitude_entries": [],
            "rescheduled_tasks": [],
            "alarm_acknowledged": False,
            "nag_count": 0,
            "routine_phase": "",
        }

        result = await routine_graph.ainvoke(routine_state)
        state["response"] = result.get("asta_response", "Done, boss.")
        state["task_data"] = result.get("task_data", {}) or {}
    except Exception as e:
        logger.error(f"[routine_workflow] {e}", exc_info=True)
        state["response"] = f"Boss, I hit a snag handling that routine task: {e}"
        state["error"] = str(e)
    return state


async def research_workflow(state: SupervisorState) -> SupervisorState:
    """Conversational research: clarify angle (interrupt) -> research -> synthesize -> Notion.

    Runs in this checkpointed node so interrupt() can pause/resume on the thread_id.
    The synthesized result is held in `state["research_context"]` so the Day 3
    content-chaining step can reuse it on the same thread.
    """
    from backend.app.workflows.research_manager import handle_research_turn
    from langgraph.errors import GraphInterrupt

    try:
        result = await handle_research_turn(state.get("user_input", ""))
    except GraphInterrupt:
        raise  # must propagate so the graph pauses for clarification
    except Exception as e:
        logger.error(f"[research_workflow] {e}", exc_info=True)
        state["response"] = f"Boss, research hit a snag: {e}"
        state["error"] = str(e)
        return state

    state["response"] = result.get("response", "Done, boss.")
    state["task_data"] = result.get("task_data", {}) or {}
    if result.get("notion_page_id"):
        state["task_data"]["notion_page_id"] = result["notion_page_id"]
    if result.get("research_context"):
        state["research_context"] = result["research_context"]
    return state


async def content_workflow(state: SupervisorState) -> SupervisorState:
    """Conversational content creation: chains off `research_context` if present.

    Runs in this checkpointed node so interrupt() (review / regenerate, and
    optionally "research first?") can pause/resume on the thread_id.
    """
    from backend.app.workflows.content_manager import handle_content_turn
    from langgraph.errors import GraphInterrupt

    try:
        result = await handle_content_turn(
            state.get("user_input", ""), state.get("research_context") or {},
            state.get("content_state") or {},
        )
    except GraphInterrupt:
        raise  # must propagate so the graph pauses for clarification/review
    except Exception as e:
        logger.error(f"[content_workflow] {e}", exc_info=True)
        state["response"] = f"Boss, content creation hit a snag: {e}"
        state["error"] = str(e)
        state["content_state"] = {}  # don't get stuck in awaiting_review on error
        return state

    state["response"] = result.get("response", "Done, boss.")
    state["task_data"] = result.get("task_data", {}) or {}
    state["content_state"] = result.get("content_state", {}) or {}
    if result.get("notion_page_id"):
        state["task_data"]["notion_page_id"] = result["notion_page_id"]
    return state


async def other_workflow(state: SupervisorState) -> SupervisorState:
    """Natural-language chat fallback."""
    text = state.get("user_input", "")
    try:
        # Inject recalled long-term memory (from memory_engine) into the prompt.
        system = CHAT_SYSTEM
        mem = (state.get("memory_context") or "").strip()
        if mem:
            system = f"{CHAT_SYSTEM}\n\n{mem}"
        state["response"] = await acomplete(system, text, task="quick", max_tokens=300)
    except Exception as e:
        logger.error(f"[other_workflow] {e}")
        state["response"] = "Sorry boss, I couldn't process that right now."
        state["error"] = str(e)
    return state


async def save_session(state: SupervisorState) -> SupervisorState:
    """Persist the turn into the unified memory layer (entities → Neo4j,
    summary → Pinecone, full session → Mongo) via memory_engine.

    Fired in the background so the heavy write (entity extraction + embed +
    graph writes) never blocks the user's response. memory_engine isolates
    per-layer failures internally, so a down layer won't lose the others.
    """
    try:
        from memory import memory_engine

        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": state.get("user_input", "")})
        messages.append({"role": "assistant", "content": state.get("response", "")})

        _fire(memory_engine.save_session(
            session_id=state.get("session_id", ""),
            workflow_type=state.get("intent", "chat") or "chat",
            messages=messages,
            start_time=state.get("start_time") or datetime.utcnow().isoformat(),
            notion_page_id=(state.get("task_data") or {}).get("notion_page_id", ""),
        ))
        logger.info(f"[save_session] memory write fired for {state.get('session_id','')}")
    except Exception as e:
        # Never fail the turn because persistence failed.
        logger.warning(f"[save_session] skipped: {e}")
    return state


# ── GRAPH ────────────────────────────────────────────────────────────────────

def _build():
    g = StateGraph(SupervisorState)
    g.add_node("classify_intent", classify_intent)
    g.add_node("routine_workflow", routine_workflow)
    g.add_node("research_workflow", research_workflow)
    g.add_node("content_workflow", content_workflow)
    g.add_node("other_workflow", other_workflow)
    g.add_node("save_session", save_session)

    g.add_edge(START, "classify_intent")
    g.add_conditional_edges("classify_intent", route_to_workflow, {
        "routine_workflow": "routine_workflow",
        "research_workflow": "research_workflow",
        "content_workflow": "content_workflow",
        "other_workflow": "other_workflow",
    })
    g.add_edge("routine_workflow", "save_session")
    g.add_edge("research_workflow", "save_session")
    g.add_edge("content_workflow", "save_session")
    g.add_edge("other_workflow", "save_session")
    g.add_edge("save_session", END)
    return g


_builder = _build()
_compiled = None


def get_supervisor_graph():
    """Compile once with the active checkpointer."""
    global _compiled
    if _compiled is None:
        _compiled = _builder.compile(checkpointer=get_checkpointer())
        logger.info("Supervisor graph compiled with checkpointer")
    return _compiled


def _pending_interrupt_question(result: dict):
    """If a graph result carries a pending interrupt, return its question text."""
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if not interrupts:
        return None
    val = interrupts[0].value
    if isinstance(val, dict):
        return val.get("question") or str(val)
    return str(val)


async def run_supervisor_graph(session_id: str, user_input: str, messages: list = None) -> dict:
    """Entry point used by HTTP / WebSocket routes.

    Multi-turn aware: if this thread is paused on a clarification question, the
    incoming message is fed back as the interrupt response (Command(resume=...)).
    """
    from langgraph.types import Command

    graph = get_supervisor_graph()
    config = {"configurable": {"thread_id": session_id or "default"}}

    # Is this thread waiting on a clarification (interrupt)? If so, resume it.
    # Note: after a SECOND interrupt() raised during a resumed node execution,
    # `snap.next` can be `()` even though `snap.interrupts` is non-empty — so
    # `interrupts` alone is the reliable signal here.
    resuming = False
    try:
        snap = await graph.aget_state(config)
        if snap and getattr(snap, "interrupts", None):
            resuming = True
    except Exception as e:
        logger.debug(f"[run_supervisor_graph] state check skipped: {e}")

    try:
        if resuming:
            logger.info(f"[run_supervisor_graph] resuming thread {session_id} with reply")
            final = await graph.ainvoke(Command(resume=user_input), config=config)
        else:
            # Retrieve long-term memory for this turn (Neo4j cluster → Pinecone
            # vector → Mongo), formatted for prompt injection. Best-effort.
            memory_context = ""
            try:
                from memory import memory_engine
                ctx = await memory_engine.get_context_for_session(
                    session_id=session_id or "default",
                    user_input=user_input,
                    workflow_type="general",
                )
                memory_context = memory_engine.format_context_for_prompt(ctx)
                if memory_context:
                    logger.info(f"[run_supervisor_graph] injected {len(memory_context)} chars of memory context")
            except Exception as mem_err:
                logger.warning(f"[run_supervisor_graph] memory fetch skipped: {mem_err}")

            initial: SupervisorState = {
                "user_input": user_input,
                "session_id": session_id,
                "messages": messages or [],
                "intent": "",
                "task_data": {},
                "response": "",
                "memory_context": memory_context,
                "start_time": datetime.utcnow().isoformat(),
            }
            final = await graph.ainvoke(initial, config=config)

        # Did the graph pause to ask a clarifying question?
        question = _pending_interrupt_question(final)
        if question:
            return {
                "session_id": session_id,
                "user_input": user_input,
                "intent": final.get("intent", "other") if isinstance(final, dict) else "other",
                "response": question,
                "task_data": {},
                "awaiting_clarification": True,
            }
        return dict(final)
    except Exception as e:
        logger.error(f"[run_supervisor_graph] {e}", exc_info=True)
        return {
            "session_id": session_id,
            "user_input": user_input,
            "intent": "error",
            "response": f"I hit an error processing that, boss: {e}",
            "task_data": {},
            "error": str(e),
        }
