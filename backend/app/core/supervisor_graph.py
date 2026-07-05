"""
ASTA Supervisor — real LangGraph StateGraph.

Flow:  START → classify_intent → (route) → [routine_workflow | other_workflow] → save_session → END

The supervisor classifies intent, routes to a workflow, then persists the turn
to MongoDB. Compiled with a checkpointer so every step is checkpointed per
session (thread_id = session_id).
"""
import logging
import re
import time
from datetime import datetime, date
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from backend.app.core.llm_factory import acomplete
from backend.app.core.checkpointer import get_checkpointer

logger = logging.getLogger("SupervisorGraph")

VALID_INTENTS = ("routine", "research", "content", "linkedin", "other")

CHAT_SYSTEM = (
    "You are ASTA, Kartik's personal AI assistant. Warm, sharp, concise. "
    "Call him 'boss'. Reply in natural language, never JSON. Max 80 words. "
    "If Kartik asks you to recall something and the context below doesn't "
    "contain it, say you don't have that on record — never guess or invent details."
)

# Fast keyword paths for classify_intent — also consulted by ws_transport.py to
# decide whether a WS turn should be routed through the supervisor graph.
ROUTINE_KEYWORDS = ["remind", "remimder", "reminder", "schedule", "task", "tasks", "add a",
                    "morning", "night", "wake", "alarm", "plan my day", "to-do", "todo",
                    # task management: list / complete / reschedule
                    "my list", "my plan", "my day", "what's on", "whats on", "agenda",
                    "what do i have", "mark ", "done", "complete", "finished",
                    "move the", "move my", "reschedule", "postpone", "push the"]

CONTENT_KEYWORDS = ["linkedin", "instagram", "youtube", "carousel", "reel script", "video script",
                    "write a post", "write a script", "make me a post", "make a post", "create a post",
                    "draft a post", "post about", "content for", "caption for",
                    "remember this for my post", "remember this for my content"]

# ── Memory routing ────────────────────────────────────────────────────────────
# Keyword fast-path: classify "other" turns so only recall/project turns hit
# the Neo4j+Pinecone stack.  Casual/feedback turns skip it entirely and return
# a warm reply without the ~200-500 ms memory latency.

_RECALL_KW = [
    "what did i", "did i tell", "do you remember", "can you recall",
    "what was ", "when did i", "what project", "what are my projects",
    "remind me what", "remind me who", "remind me which", "what have i",
    "my research", "my notes on", "what is my project", "what's my project",
    "whats my project", "what is my ", "what's my ", "whats my ",
    "last time i", "previously", "earlier you", "earlier i said",
    "what's the status", "whats the status", "tell me about my",
    "who is my ", "when was ", "where did i",
]

_CASUAL_KW = [
    "how are you", "how's it going", "how is it going", "what's up", "whats up",
    "thanks ", "thank you", "sounds good", "got it", "nice",
    "cool ", "awesome", "lol", "haha", "hm ", "hmm",
    "hey there", "hey asta", "hi asta", "nothing much", "all good",
    "you're great", "you are great", "that's great", "thats great",
]

CASUAL_CHAT_SYSTEM = (
    "You are ASTA, Kartik's personal AI assistant. Warm, cheerful, concise. "
    "Call him 'boss'. Reply in natural language, never JSON. Max 60 words."
)


def should_search_memory(text: str) -> bool:
    """True if this turn needs long-term memory context.

    Keyword fast-path: recall signals → True; short/casual signals → False;
    anything ambiguous → True (safe default, never miss context on real questions).
    """
    low = (text or "").lower()
    if any(k in low for k in _RECALL_KW):
        return True
    if len(low.split()) <= 3:
        return False
    if any(k in low for k in _CASUAL_KW):
        return False
    return True


# ── STATE ────────────────────────────────────────────────────────────────────

from backend.app.core.graph_state import SupervisorState


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
    # Recall questions about the past ("what did I research about X", "remind me
    # what ...", "what was my project ...") are ALWAYS "other" (→ other_workflow
    # with memory fetch).  Must be checked BEFORE routine/research fast-paths so
    # a phrase like "what did I research about X" doesn't misfire as research.
    is_recall_phrasing = bool(
        re.search(r"remind\w* me (what|who|which|why|how|when|where)\b", low)
        or re.search(r"\bwhat did i (research|learn|find|say|tell|do|write|build)\b", low)
        or re.search(r"\b(did i tell|when did i|what was i|what have i|what is my project)\b", low)
    )
    if is_recall_phrasing:
        state["intent"] = "other"
        return state
    if any(k in low for k in ROUTINE_KEYWORDS):
        state["intent"] = "routine"
        return state

    # Fast keyword path for content creation (LinkedIn/YouTube/Instagram posts
    # and scripts), including the "remember this for my posts" pref-update phrase.
    if any(k in low for k in CONTENT_KEYWORDS):
        state["intent"] = "content"
        return state

    try:
        raw = await acomplete(
            system=(
                "Classify the user's message into exactly one label: "
                "routine, research, content, or other.\n"
                "routine = the user wants to CREATE, LIST, COMPLETE, or RESCHEDULE a "
                "to-do/reminder/task, or asks for their daily plan/agenda/morning brief.\n"
                "research = an explicit request to look something up / research a topic in depth.\n"
                "content = social media content creation (LinkedIn post, YouTube script, Instagram caption).\n"
                "other = everything else: general conversation, questions, statements of fact, "
                "preferences, opinions, or asking the assistant to recall something it was told before.\n"
                "Examples: 'what is my project codename?' -> other. "
                "'remember that I like oat milk' -> other. "
                "'what did I research about X?' -> other (recall question, not new research). "
                "'add a task to call mom' -> routine. "
                "'what's on my list today' -> routine.\n"
                "Reply with ONLY the label."
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

    # Morning brief / night planning / alarm → RoutineEngine
    try:
        from backend.app.workflows.routine_engine import RoutineEngine
        engine = RoutineEngine()
        session_id = state.get("session_id", "routine-session")
        
        if any(w in low for w in ["night planning", "plan tomorrow", "end of day", "wrap up", "good night"]):
            result_text = await engine.run_night_routine(session_id)
        else:
            from backend.app.services.preferences_service import preferences_service
            prefs = await preferences_service.get(session_id)
            user_city = prefs.get("city", "San Francisco")
            result_text = await engine.run_morning_routine(user_city, session_id)

        state["response"] = result_text
        state["task_data"] = {}
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
    """Natural-language chat fallback with dynamic memory routing.

    Casual/feedback turns skip Neo4j+Pinecone entirely and return instantly.
    Recall/project turns fetch long-term memory, then reply with grounded context.
    Decision is keyword-first (zero LLM cost) — see should_search_memory().
    """
    text = state.get("user_input", "")
    t0 = time.perf_counter()
    try:
        system = CHAT_SYSTEM
        # memory_context is empty now (no pre-fetch in run_supervisor_graph).
        # Decide here whether this turn needs the memory stack.
        if should_search_memory(text):
            try:
                from memory import memory_engine
                ctx = await memory_engine.get_context_for_session(
                    session_id=state.get("session_id") or "default",
                    user_input=text,
                    workflow_type="general",
                )
                mem = (memory_engine.format_context_for_prompt(ctx) or "").strip()
                dt = time.perf_counter() - t0
                if mem:
                    system = f"{CHAT_SYSTEM}\n\n{mem}"
                    logger.info(
                        f"[other_workflow] RECALL path — memory fetch {dt:.3f}s, "
                        f"{len(mem)} chars injected"
                    )
                else:
                    logger.info(f"[other_workflow] RECALL path — memory fetch {dt:.3f}s, empty context")
            except Exception as mem_err:
                logger.warning(f"[other_workflow] memory fetch skipped: {mem_err}")
        else:
            system = CASUAL_CHAT_SYSTEM
            dt = time.perf_counter() - t0
            logger.info(f"[other_workflow] CASUAL path — no memory search ({dt:.3f}s so far)")

        state["response"] = await acomplete(system, text, task="quick", max_tokens=300)
        total = time.perf_counter() - t0
        logger.info(f"[other_workflow] total {total:.3f}s for '{text[:40]}'")
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


async def is_awaiting_resume(session_id: str) -> bool:
    """True if this thread is paused on an interrupt() or mid-content-review
    (content_state.phase == "awaiting_review"), so the next message must be
    routed straight back into run_supervisor_graph regardless of keywords.
    Used by ws_transport.py to decide should_use_workflow before classification."""
    if not session_id:
        return False
    try:
        graph = get_supervisor_graph()
        config = {"configurable": {"thread_id": session_id}}
        snap = await graph.aget_state(config)
        if not snap:
            return False
        if getattr(snap, "interrupts", None):
            return True
        values = getattr(snap, "values", None) or {}
        if (values.get("content_state") or {}).get("phase") == "awaiting_review":
            return True
        return False
    except Exception as e:
        logger.debug(f"[is_awaiting_resume] check skipped: {e}")
        return False


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

    t_start = time.perf_counter()
    try:
        if resuming:
            logger.info(f"[run_supervisor_graph] resuming thread {session_id} with reply")
            final = await graph.ainvoke(Command(resume=user_input), config=config)
        else:
            # memory_context intentionally left empty here.  Dynamic routing in
            # other_workflow decides per-turn whether to fetch (casual → skip,
            # recall → fetch).  This removes ~200-500 ms of blocking Neo4j/
            # Pinecone latency from every casual turn.
            initial: SupervisorState = {
                "user_input": user_input,
                "session_id": session_id,
                "messages": messages or [],
                "intent": "",
                "task_data": {},
                "response": "",
                "memory_context": "",
                "start_time": datetime.utcnow().isoformat(),
            }
            final = await graph.ainvoke(initial, config=config)
        logger.info(f"[run_supervisor_graph] turn done in {time.perf_counter() - t_start:.3f}s")

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
