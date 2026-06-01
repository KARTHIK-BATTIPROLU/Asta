"""
ASTA Research Workflow Graph
Handles deep research with conversation, web search, and synthesis.
"""
import logging
from langgraph.graph import StateGraph, START, END

from backend.app.core.state import ResearchState, add_stage
from backend.app.core.llm_router import llm_router
from backend.app.services.research_service import research_service
from backend.app.services.notion_service import notion_service

logger = logging.getLogger(__name__)

RESEARCH_CONV_SYSTEM = """You are ASTA in deep research mode. Professional, curious, thorough.
Ask ONE sharp probing question at a time to understand Karthik's angle on the topic.
Build on what he says. Call him "boss". Max 50 words per response."""

SYNTHESIS_SYSTEM = """You are ASTA synthesizing research for Karthik.
Karthik thinks in first principles. He wants: what's true, what matters, what to do.
No fluff. Be direct. Reference his perspective from the conversation."""


# ── NODES ─────────────────────────────────────────────────────────────────

async def extract_topic(state: ResearchState) -> ResearchState:
    """Extract research topic from user input."""
    topic_result = await llm_router.invoke_with_system(
        "intent_classification",
        "Extract the research topic from this message. Return only the topic, max 10 words.",
        state.get("current_input", "")
    )
    state["topic"] = topic_result.strip()
    state["conversation_turn_count"] = 0
    state["research_complete"] = False
    state["intermediate_stages"] = add_stage(state, "topic_extracted", "done", state["topic"])
    return state


async def conversation_turn(state: ResearchState) -> ResearchState:
    """Conduct probing conversation to understand user's angle."""
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    turn_count = state.get("conversation_turn_count", 0) + 1
    state["conversation_turn_count"] = turn_count
    
    memory_ctx = state.get("memory_context", "")
    
    probing_questions = [
        f"What's your current understanding of {topic}? What angle interests you most?",
        "What specifically do you want to walk away knowing?",
        "Any personal experience or context with this? That'll help me tailor the research.",
    ]
    
    if turn_count <= len(probing_questions) and turn_count == 1:
        state["asta_response"] = probing_questions[0]
    else:
        convo_so_far = "\n".join([
            f"{m['role'].upper()}: {str(m.get('content',''))[:300]}" 
            for m in messages[-6:]
        ])
        response = await llm_router.invoke_with_system(
            "voice_response",
            f"{RESEARCH_CONV_SYSTEM}\n{memory_ctx}",
            f"Topic: {topic}\nConversation so far:\n{convo_so_far}\n\n"
            f"Ask the next probing question OR if you have enough context (3+ turns), "
            f"say 'I have enough context — ready to research when you are boss.'"
        )
        state["asta_response"] = response
    
    state["intermediate_stages"] = add_stage(state, "conversation", "turn", f"turn {turn_count}")
    return state


def check_research_ready(state: ResearchState) -> str:
    """Check if ready to start research or continue conversation."""
    user_input = state.get("current_input", "").lower()
    turn_count = state.get("conversation_turn_count", 0)
    
    trigger_words = [
        "research now", "go find", "look it up", "start research", 
        "that's enough", "dive in", "go ahead", "yes research", "do it"
    ]
    if any(w in user_input for w in trigger_words):
        return "execute_research"
    if turn_count >= 5:
        return "execute_research"
    return "conversation_turn"


async def generate_queries(state: ResearchState) -> ResearchState:
    """Generate search queries based on topic and conversation."""
    topic = state.get("topic", "")
    messages = state.get("messages", [])
    convo = "\n".join([
        f"{m['role'].upper()}: {str(m.get('content',''))[:200]}" 
        for m in messages[-8:]
    ])
    
    queries_raw = await llm_router.invoke_with_system(
        "intent_classification",
        "Generate 4 precise web search queries targeting official documentation, "
        "research papers, and authoritative sources. Return one query per line, no numbering.",
        f"Topic: {topic}\nConversation context:\n{convo}"
    )
    queries = [q.strip() for q in queries_raw.strip().split("\n") if q.strip()][:4]
    state["search_queries"] = queries
    state["intermediate_stages"] = add_stage(
        state, "queries_generated", "done", f"{len(queries)} queries"
    )
    return state


async def execute_research(state: ResearchState) -> ResearchState:
    """Execute web research and arxiv search."""
    topic = state.get("topic", "")
    queries = state.get("search_queries", [topic])
    state["intermediate_stages"] = add_stage(state, "web_research", "started", "")
    
    research = await research_service.deep_research(topic, queries)
    
    # Also check arxiv for technical topics
    arxiv_results = await research_service.search_arxiv(topic)
    
    state["filtered_sources"] = research.get("sources", [])
    state["raw_search_results"] = arxiv_results
    state["intermediate_stages"] = add_stage(
        state, "web_research", "done",
        f"{research['total_sources']} sources + {len(arxiv_results)} papers"
    )
    return state


async def synthesize(state: ResearchState) -> ResearchState:
    """Synthesize research findings with conversation context."""
    topic = state.get("topic", "")
    sources = state.get("filtered_sources", [])
    messages = state.get("messages", [])
    arxiv = state.get("raw_search_results", [])
    
    # Build conversation summary
    user_messages = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    convo_text = "\n".join(f"- {m[:300]}" for m in user_messages)
    
    # Build sources text
    sources_text = ""
    for s in sources[:6]:
        sources_text += f"\n\nSOURCE [{s.get('url','')}]:\n{s.get('content','')[:1500]}"
    
    arxiv_text = "\n".join([
        f"- {p['title']}: {p['summary'][:200]}" for p in arxiv[:3]
    ])
    
    synthesis = await llm_router.invoke_with_system(
        "research_synthesis",
        f"""{SYNTHESIS_SYSTEM}

Topic: {topic}

What Karthik discussed in the conversation:
{convo_text}

Research sources:
{sources_text}

Academic papers found:
{arxiv_text if arxiv_text else "None"}""",
        """Synthesize this into THREE sections. Be thorough but direct.

## CONVERSATION SUMMARY
(Bullet points: what Karthik said, his perspective, what he wants to understand)

## RESEARCH POINTS  
(Bullet points: key findings from sources, include source URLs, important stats/facts)

## COMBINED SOLUTION
(Synthesized insight combining his angle + research findings. First-principles, actionable. This is the "so what" section.)"""
    )
    
    # Parse the three sections
    sections = synthesis.split("##")
    
    def extract_section(sections, keyword):
        for s in sections:
            if keyword.upper() in s.upper():
                return s.split("\n", 1)[1].strip() if "\n" in s else s.strip()
        return ""
    
    conv_summary = extract_section(sections, "CONVERSATION")
    research_points_text = extract_section(sections, "RESEARCH")
    combined = extract_section(sections, "COMBINED")
    
    state["conversation_summary"] = conv_summary
    state["research_points"] = [
        p.strip().lstrip("-").strip() 
        for p in research_points_text.split("\n") 
        if p.strip()
    ]
    state["combined_solution"] = combined
    state["intermediate_stages"] = add_stage(
        state, "synthesis", "done", f"{len(state['research_points'])} points"
    )
    return state


async def save_research_to_notion(state: ResearchState) -> ResearchState:
    """Save research results to Notion."""
    page_id = await notion_service.create_research_page(
        topic=state.get("topic", ""),
        conversation_summary=state.get("conversation_summary", ""),
        research_points=state.get("research_points", []),
        combined_solution=state.get("combined_solution", "")
    )
    state["notion_page_id"] = page_id
    combined_snippet = state.get("combined_solution", "")[:300]
    state["asta_response"] = (
        f"Research done, boss. Saved to Notion. Here's the key insight:\n\n"
        f"{combined_snippet}...\n\nCheck Notion for the full breakdown."
    )
    state["is_complete"] = True
    state["intermediate_stages"] = add_stage(
        state, "saved_to_notion", "done", page_id[:8] if page_id else ""
    )
    
    # Save to memory
    try:
        from memory import memory_engine
        await memory_engine.on_user_message(
            state.get("session_id", ""), 
            f"Researched: {state.get('topic','')}"
        )
    except:
        pass
    
    return state


# ── GRAPH ──────────────────────────────────────────────────────────────────

def build_research_graph():
    """Build and compile the research workflow graph."""
    graph = StateGraph(ResearchState)
    
    # Add nodes
    graph.add_node("extract_topic", extract_topic)
    graph.add_node("conversation_turn", conversation_turn)
    graph.add_node("generate_queries", generate_queries)
    graph.add_node("execute_research", execute_research)
    graph.add_node("synthesize", synthesize)
    graph.add_node("save_to_notion", save_research_to_notion)
    
    # Add edges
    graph.add_edge(START, "extract_topic")
    graph.add_edge("extract_topic", "conversation_turn")
    graph.add_conditional_edges("conversation_turn", check_research_ready, {
        "conversation_turn": "conversation_turn",
        "execute_research": "generate_queries",
    })
    graph.add_edge("generate_queries", "execute_research")
    graph.add_edge("execute_research", "synthesize")
    graph.add_edge("synthesize", "save_to_notion")
    graph.add_edge("save_to_notion", END)
    
    return graph.compile()


# Global compiled graph
research_graph = build_research_graph()
