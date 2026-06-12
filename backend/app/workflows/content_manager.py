"""
ASTA conversational content manager (Day 3).

Runs INSIDE the supervisor graph's `content_workflow` node. Uses exactly ONE
`interrupt()` call ("research first or raw?"), bound to the checkpointed
thread (thread_id = session_id) and resumed via Command(resume=...).

NOTE: LangGraph 1.1.3 does not reliably checkpoint a SECOND interrupt() raised
during a resumed execution of the same node (snap.next comes back empty even
though snap.interrupts is non-empty, so a third invocation can't resume it).
So the review/regenerate step is NOT a second interrupt() — instead the draft
+ "looks good or want changes?" is returned as a normal response, and
`content_state["phase"] = "awaiting_review"` is persisted on the thread
(LastValue channel). The supervisor's classify_intent short-circuits the next
turn straight back into this workflow based on that phase.

Flow: detect platform -> use prior `research_context` if present, else
interrupt "research first or raw?" -> generate post/script per content_style +
platform prefs -> return draft for review (phase=awaiting_review) -> next turn:
regenerate on feedback (or finalize on approval) -> 2 images via image_service
-> Notion Content DB page.

"Remember this for my posts" is handled here too, short-circuiting straight
to preferences_service.update_from_voice("content_style", ...).
"""
import json
import logging
import re

from langgraph.types import interrupt

from backend.app.core.llm_factory import acomplete
from backend.app.services.notion_service import notion_service
from backend.app.services.preferences_service import preferences_service
from backend.app.services.image_service import image_service
from backend.app.services.research_service import research_service

logger = logging.getLogger("ContentManager")

_PREF_UPDATE_KW = [
    "remember this for my post", "remember this for my content",
    "remember my style", "update my content style",
]

_PLATFORM_KW = {
    "youtube": ["youtube", "video script", "yt video"],
    "instagram": ["instagram", "insta", "reel", "carousel"],
}

_APPROVAL_KW = ["good", "great", "perfect", "yes", "approve", "approved", "finalize",
                "ship it", "lgtm", "looks good", "love it", "nice", "awesome", "done"]
_REJECT_KW = ["no", "change", "revise", "redo", "different", "shorter", "longer",
              "more", "less", "remove", "instead", "rewrite", "again", "tone down", "make it"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _detect_platform(low: str) -> str:
    for platform, kws in _PLATFORM_KW.items():
        if any(k in low for k in kws):
            return platform
    return "linkedin"


def _is_pref_update(low: str) -> bool:
    return any(k in low for k in _PREF_UPDATE_KW)


def _is_approval(reply: str) -> bool:
    low = (reply or "").strip().lower()
    if not low:
        return True
    if any(k in low for k in _REJECT_KW):
        return False
    if any(k in low for k in _APPROVAL_KW):
        return True
    return True  # ambiguous -> proceed rather than loop forever


def _looks_like_content_not_topic(text: str) -> bool:
    low = text.lower()
    return (
        len(text) > 80
        or "\n" in text
        or any(p in low for p in ("here's", "here is", "**", "title:", "post:", "script:", "caption:"))
    )


async def _extract_topic(user_input: str) -> str:
    raw = await acomplete(
        system=(
            "Extract ONLY the subject/topic the user wants content written about - a short "
            "noun phrase, max 8 words. Do NOT write the post/script/caption yourself, do not "
            "add a title, no markdown, no quotes - just the bare topic phrase."
        ),
        user=f'Message: "{user_input}"\n\nTopic (short noun phrase only):',
        task="quick", temperature=0.0, max_tokens=20,
    )
    topic = (raw or "").strip().strip('"').splitlines()[0].strip()
    if not topic or _looks_like_content_not_topic(topic):
        return user_input
    return topic


async def _merged_prefs(platform: str) -> dict:
    style = await preferences_service.get("content_style")
    platform_prefs = await preferences_service.get(platform)
    return {"style": style or {}, "platform": platform_prefs or {}}


def _context_from_research(research_context: dict) -> str:
    parts = []
    if research_context.get("angle"):
        parts.append(f"Karthik's angle: {research_context['angle']}")
    if research_context.get("combined_solution"):
        parts.append(f"Combined insight: {research_context['combined_solution']}")
    points = research_context.get("research_points") or []
    if points:
        parts.append("Research points:\n" + "\n".join(f"- {p}" for p in points[:8]))
    return "\n\n".join(parts)


async def _quick_research_context(topic: str) -> dict:
    """Lightweight research (no further interrupt) for the 'research first' path."""
    from backend.app.workflows.research_manager import _generate_queries, _synthesize

    queries = await _generate_queries(topic, "general overview")
    research = await research_service.deep_research(topic, queries)
    arxiv_results = await research_service.search_arxiv(topic)
    return await _synthesize(topic, "general overview", research.get("sources", []), arxiv_results)


def _parse_json_block(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        # strict=False: LLMs routinely emit literal newlines inside JSON string
        # values, which the default strict JSON parser rejects.
        parsed = json.loads(raw.strip(), strict=False)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _fallback_draft(platform: str, raw: str, topic: str) -> dict:
    tag = "#" + re.sub(r"[^A-Za-z0-9]", "", topic)[:30] or "#ASTA"
    if platform == "youtube":
        return {"script": raw, "title_ideas": [topic], "tags": [topic]}
    if platform == "instagram":
        return {"caption": raw[:300], "hashtags": [tag], "slides": [raw]}
    return {"post_body": raw, "hashtags": [tag]}


def _body_for(platform: str, draft: dict) -> str:
    return {
        "linkedin": draft.get("post_body", ""),
        "youtube": draft.get("script", ""),
        "instagram": draft.get("caption", ""),
    }[platform]


def _preview_for(platform: str, draft: dict) -> str:
    body = _body_for(platform, draft)
    extra = ""
    hashtags = draft.get("hashtags") or []
    if hashtags:
        extra = "\n\n" + " ".join(hashtags[:10])
    return (body[:800] + extra)[:900]


def _platform_json_spec(platform: str, pf: dict) -> str:
    if platform == "youtube":
        return (
            'Return ONLY valid JSON: {"script": "...", "title_ideas": ["...", "...", "..."], "tags": ["...", ...]}\n'
            f"Target length: ~{pf.get('target_length_minutes', 10)} minutes. "
            f"Structure: {pf.get('script_format', '')}"
        )
    if platform == "instagram":
        return (
            'Return ONLY valid JSON: {"caption": "...", "hashtags": ["...", ...], "slides": ["...", ...]}\n'
            f"Slide count: {pf.get('slide_count', 7)}. Slide structure: {', '.join(pf.get('slide_structure', []))}. "
            f"Caption max chars: {pf.get('caption_max_chars', 300)}. Include {pf.get('hashtag_count', 25)} hashtags."
        )
    return (
        'Return ONLY valid JSON: {"post_body": "...", "hashtags": ["...", ...]}\n'
        f"Format: {pf.get('post_format', '')}. Include exactly {pf.get('hashtag_count', 5)} hashtags."
    )


async def _generate_draft(platform: str, topic: str, context_text: str, prefs: dict,
                           feedback: str = None, previous: dict = None) -> dict:
    style, pf = prefs["style"], prefs["platform"]
    system = (
        f"You are ghostwriting {platform} content in Karthik's voice (never address him as "
        f"'boss' inside the content itself, that's only how he talks to ASTA).\n"
        f"Tone: {pf.get('tone') or style.get('tone', '')}\n"
        f"Structure: {style.get('structure', '')}\n"
        f"Hook styles: {', '.join((pf.get('hook_styles') or []) + (style.get('hooks') or []))}\n"
        f"Emoji policy: {pf.get('emoji_usage') or style.get('emoji', '')}\n"
        f"Avoid: {', '.join((style.get('avoid') or []) + (pf.get('avoid') or []))}\n\n"
        f"{_platform_json_spec(platform, pf)}"
    )
    user = f"Topic: {topic}\n\nContext:\n{context_text[:2500] if context_text else '(none provided — use general knowledge)'}"
    if feedback:
        user += (
            f"\n\nPrevious draft:\n{json.dumps(previous or {})[:1500]}\n\n"
            f"Karthik's feedback: {feedback}\nRevise the draft accordingly, keep the same JSON shape."
        )

    task = {"linkedin": "post_generation", "youtube": "script_generation",
            "instagram": "content_generation"}[platform]
    raw = await acomplete(system, user, task=task, temperature=0.7, max_tokens=1200)
    parsed = _parse_json_block(raw) or _fallback_draft(platform, raw, topic)
    if parsed.get("hashtags"):
        parsed["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in parsed["hashtags"]]
    return parsed


async def _log_to_notion(platform: str, topic: str, draft: dict, images: list,
                          context_text: str, research_points: list) -> str:
    if platform == "youtube":
        return await notion_service.create_youtube_page(
            topic=topic, script=draft.get("script", ""),
            research_points=research_points or [],
            metadata={"title_ideas": draft.get("title_ideas", []), "tags": draft.get("tags", [])},
            images=images,
        )
    if platform == "instagram":
        return await notion_service.create_instagram_page(
            topic=topic, caption=draft.get("caption", ""),
            hashtags=draft.get("hashtags", []), slides=draft.get("slides", []),
            images=images,
        )
    return await notion_service.create_linkedin_page(
        topic=topic, post_body=draft.get("post_body", ""),
        hashtags=draft.get("hashtags", []), discussion_summary=context_text[:1500],
        images=images,
    )


# ── Entry point ─────────────────────────────────────────────────────────────

async def handle_content_turn(user_input: str, research_context: dict, content_state: dict) -> dict:
    """Run one content-creation turn.

    `content_state` is persisted across turns on the thread (LastValue channel).
    If `content_state["phase"] == "awaiting_review"`, this turn's `user_input` is
    treated as review feedback for the stored draft (regenerate-or-finalize).
    Otherwise this is a fresh content request: chain off research_context if
    present, else interrupt() once asking "research first or raw?".

    May raise GraphInterrupt (via interrupt()) — the caller must let it propagate.
    Returns {"response", "task_data", "notion_page_id", "content_state"}.
    """
    content_state = content_state or {}

    if content_state.get("phase") == "awaiting_review":
        return await _resume_after_review(user_input, content_state)

    low = user_input.lower()

    if _is_pref_update(low):
        msg = await preferences_service.update_from_voice("content_style", user_input)
        return {"response": f"Got it, boss. {msg}", "task_data": {}, "content_state": {}}

    platform = _detect_platform(low)
    research_context = research_context or {}
    research_points = research_context.get("research_points") or []

    if research_context.get("topic"):
        topic = research_context["topic"]
        context_text = _context_from_research(research_context)
        logger.info(f"[content_manager] chaining off research_context topic={topic!r}")
    else:
        topic = await _extract_topic(user_input)
        kind = "script" if platform != "linkedin" else "post"
        reply = interrupt({
            "question": (
                f"Got it, boss — a {platform} {kind} about '{topic}'. Want me to research it "
                f"first for more depth, or write it straight from what you've told me?"
            ),
            "field": "content_research_or_raw",
        })
        reply = (reply or "").strip().lower()
        if any(k in reply for k in ["research", "yes", "look", "first", "deep", "dig"]):
            synthesized = await _quick_research_context(topic)
            context_text = _context_from_research(synthesized)
            research_points = synthesized.get("research_points") or []
        else:
            context_text = user_input

    prefs = await _merged_prefs(platform)
    draft = await _generate_draft(platform, topic, context_text, prefs)
    preview = _preview_for(platform, draft)

    new_content_state = {
        "phase": "awaiting_review",
        "platform": platform,
        "topic": topic,
        "context_text": context_text,
        "research_points": research_points,
        "draft": draft,
        "prefs": prefs,
    }
    return {
        "response": f"Here's your {platform} draft, boss:\n\n{preview}\n\nLooks good, or want changes?",
        "task_data": {},
        "content_state": new_content_state,
    }


async def _resume_after_review(user_input: str, content_state: dict) -> dict:
    """Second turn: regenerate on feedback (or finalize on approval), then
    images + Notion log. Always clears content_state (phase complete)."""
    platform = content_state["platform"]
    topic = content_state["topic"]
    context_text = content_state["context_text"]
    research_points = content_state.get("research_points") or []
    prefs = content_state["prefs"]
    draft = content_state["draft"]

    if not _is_approval(user_input):
        draft = await _generate_draft(platform, topic, context_text, prefs,
                                        feedback=user_input, previous=draft)

    images = await image_service.generate_images(
        topic=topic, post_body=_body_for(platform, draft), count=2
    )

    page_id = await _log_to_notion(platform, topic, draft, images, context_text, research_points)

    preview = _preview_for(platform, draft)
    kind = "script" if platform != "linkedin" else "post"
    response = (
        f"Done, boss — your {platform} {kind} is ready and logged to the Content DB "
        f"with {len(images)} image{'s' if len(images) != 1 else ''}. Hand it to your "
        f"posting pipeline whenever.\n\n{preview[:300]}"
    )

    return {
        "response": response,
        "task_data": {"topic": topic, "platform": platform, "images": len(images)},
        "notion_page_id": page_id,
        "content_state": {},
    }
