"""
ASTA conversational research manager.

Runs INSIDE the supervisor graph's `research_workflow` node, so the single
clarifying-angle `interrupt()` here is bound to the checkpointed thread
(thread_id = session_id) and resumes correctly via Command(resume=...).

Flow: extract topic -> ask angle/depth (interrupt) -> generate queries ->
deep_research + arxiv -> synthesize (3 sections) -> Notion Research DB page.
The synthesized result is returned so the supervisor can hold it in thread
state for the Day 3 content-chaining step.
"""
import logging
import re

from langgraph.types import interrupt

from backend.app.core.llm_factory import acomplete
from backend.app.services.research_service import research_service
from backend.app.services.notion_service import notion_service

logger = logging.getLogger("ResearchManager")

SYNTHESIS_SYSTEM = (
    "You are ASTA synthesizing research for Karthik. Karthik thinks in first "
    "principles. He wants: what's true, what matters, what to do. No fluff. "
    "Be direct. Reference his stated angle from the conversation."
)


async def _extract_topic(user_input: str) -> str:
    raw = await acomplete(
        system="Extract the research topic from this message. Return only the topic, max 10 words.",
        user=user_input,
        task="quick", temperature=0.0, max_tokens=30,
    )
    return (raw or user_input).strip().strip('"')


def _clean_query_line(line: str) -> str:
    line = line.strip().lstrip("-*0123456789.").strip()
    return line.strip('"\'')


def _looks_like_preamble(line: str) -> bool:
    low = line.lower()
    return (
        len(line) > 120
        or low.endswith(":")
        or any(p in low for p in ("here are", "here's", "sure,", "queries:", "query:"))
    )


async def _generate_queries(topic: str, angle: str) -> list:
    raw = await acomplete(
        system=(
            "Output ONLY 4 web search queries, one per line. No preamble, no numbering, "
            "no quotation marks, no explanations — just the 4 queries, each a short "
            "keyword phrase (5-8 words) suitable for a search engine."
        ),
        user=f"Topic: {topic}\nKarthik's angle: {angle}",
        task="quick", temperature=0.0, max_tokens=120,
    )
    queries = [
        _clean_query_line(q) for q in (raw or "").splitlines()
        if q.strip() and not _looks_like_preamble(q)
    ]
    return queries[:4] or [topic]


# Literal markers the model must echo verbatim — far more reliable to split on
# than markdown headings, which models render inconsistently (## vs ** vs none).
_MARKERS = {
    "conversation_summary": "===CONVERSATION_SUMMARY===",
    "research_points": "===RESEARCH_POINTS===",
    "combined_solution": "===COMBINED_SOLUTION===",
}


def _split_by_markers(synthesis: str) -> dict:
    """Split the model's output on the literal === markers. Falls back to dumping
    everything into combined_solution if the model didn't echo them."""
    pattern = "(" + "|".join(re.escape(m) for m in _MARKERS.values()) + ")"
    parts = re.split(pattern, synthesis)
    sections = {}
    current = None
    for part in parts:
        marker_key = next((k for k, m in _MARKERS.items() if m == part.strip()), None)
        if marker_key:
            current = marker_key
            continue
        if current:
            sections[current] = sections.get(current, "") + part
    if not sections:
        sections["combined_solution"] = synthesis
    return {k: v.strip() for k, v in sections.items()}


async def _synthesize(topic: str, angle: str, sources: list, arxiv: list) -> dict:
    sources_text = "".join(
        f"\n\nSOURCE [{s.get('url', '')}]:\n{s.get('content', '')[:1500]}" for s in sources[:6]
    )
    arxiv_text = "\n".join(f"- {p['title']}: {p['summary'][:200]}" for p in arxiv[:3])

    synthesis = await acomplete(
        system=(
            f"{SYNTHESIS_SYSTEM}\n\nTopic: {topic}\n\nKarthik's angle: {angle}\n\n"
            f"Research sources:{sources_text}\n\n"
            f"Academic papers found:\n{arxiv_text if arxiv_text else 'None'}"
        ),
        user=(
            "Synthesize this into THREE sections, each starting with the EXACT marker "
            "line shown (on its own line, verbatim, no markdown formatting around it). "
            "Be thorough but direct.\n\n"
            f"{_MARKERS['conversation_summary']}\n"
            "(Bullet points: Karthik's angle and what he wants to understand)\n\n"
            f"{_MARKERS['research_points']}\n"
            "(Bullet points: key findings from sources, include source URLs, important stats/facts)\n\n"
            f"{_MARKERS['combined_solution']}\n"
            "(Synthesized insight combining his angle + research findings. First-principles, actionable.)"
        ),
        task="research_synthesis", temperature=0.3, max_tokens=1500,
    )

    sections = _split_by_markers(synthesis)
    conv_summary = sections.get("conversation_summary", "")
    research_points_text = sections.get("research_points", "")
    combined = sections.get("combined_solution", "")
    research_points = [p.strip().lstrip("-*").strip() for p in research_points_text.split("\n") if p.strip()]

    return {
        "conversation_summary": conv_summary,
        "research_points": research_points,
        "combined_solution": combined,
    }


async def handle_research_turn(user_input: str) -> dict:
    """Run one full research conversation: clarify -> research -> synthesize -> Notion.

    May raise GraphInterrupt (via interrupt()) — the caller must let it propagate.
    Returns {"response", "task_data", "notion_page_id", "research_context"}.
    """
    topic = await _extract_topic(user_input)
    logger.info(f"[research_manager] topic={topic!r}")

    angle = interrupt({
        "question": f"Got it, boss — researching '{topic}'. What's your angle, and how deep should I go?",
        "field": "research_angle",
    })
    angle = (angle or "").strip()

    queries = await _generate_queries(topic, angle)
    research = await research_service.deep_research(topic, queries)
    arxiv_results = await research_service.search_arxiv(topic)

    synthesized = await _synthesize(topic, angle, research.get("sources", []), arxiv_results)

    page_id = await notion_service.create_research_page(
        topic=topic,
        conversation_summary=synthesized["conversation_summary"],
        research_points=synthesized["research_points"],
        combined_solution=synthesized["combined_solution"],
    )

    combined_snippet = synthesized["combined_solution"][:300]
    response = (
        f"Research done, boss. Saved to Notion. Here's the key insight:\n\n"
        f"{combined_snippet}{'...' if len(synthesized['combined_solution']) > 300 else ''}\n\n"
        f"Check Notion for the full breakdown."
    )

    research_context = {
        "topic": topic,
        "angle": angle,
        **synthesized,
        "notion_page_id": page_id,
    }

    return {
        "response": response,
        "task_data": {"topic": topic, "notion_page_id": page_id},
        "notion_page_id": page_id,
        "research_context": research_context,
    }
