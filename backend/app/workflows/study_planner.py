"""
ASTA Study Planner — multi-turn intake + daily plan workflow.

Two capabilities:
  1. Intake — slot-filling conversation to capture subjects/topics/exam dates/budget,
     then commit to Notion via study_planner_notion.write_intake.
  2. Daily plan — generates today's sub-plan via study_planner_logic.generate_today_plan,
     persists via study_planner_notion.write_today_plan, reads it back.

State during intake lives in a module-level dict keyed by session_id. Inactive
intake sessions are dropped after 10 minutes — partial state is never committed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from backend.app.workflows import study_planner_notion as spn
from backend.app.workflows.study_planner_logic import generate_today_plan

logger = logging.getLogger("StudyPlanner")

INTAKE_TTL_SECONDS = 600  # 10 minutes


# ── intake state ────────────────────────────────────────────────────────────
@dataclass
class IntakeState:
    session_id: str
    stage: str = "subjects"          # subjects | topics | exams | hours | time | confirm | done
    subjects: list[str] = field(default_factory=list)
    cursor: int = 0                   # index into subjects (used by topics + exams stages)
    topics_by_subject: dict = field(default_factory=dict)
    exam_dates: dict = field(default_factory=dict)
    hours_per_day: Optional[int] = None
    preferred_time: Optional[str] = None
    last_activity: float = field(default_factory=time.time)

    def touch(self):
        self.last_activity = time.time()

    def is_stale(self) -> bool:
        return (time.time() - self.last_activity) > INTAKE_TTL_SECONDS


_intake_state: dict[str, IntakeState] = {}


def _drop_stale():
    for sid in [s for s, st in _intake_state.items() if st.is_stale()]:
        logger.info(f"[StudyPlanner] Dropping stale intake state for {sid[:8]}")
        _intake_state.pop(sid, None)


def has_active_intake(session_id: str) -> bool:
    _drop_stale()
    return session_id in _intake_state


# ── parsers ─────────────────────────────────────────────────────────────────
def _split_list(answer: str) -> list[str]:
    parts = re.split(r"[,;]| and ", answer or "", flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


_VALID_TIMES = {"morning", "afternoon", "evening", "mixed"}


def _parse_preferred_time(answer: str) -> Optional[str]:
    a = (answer or "").strip().lower()
    for t in _VALID_TIMES:
        if t in a:
            return t
    return None


def _parse_hours(answer: str) -> Optional[int]:
    m = re.search(r"\d+", answer or "")
    if not m:
        return None
    h = int(m.group(0))
    if 1 <= h <= 16:
        return h
    return None


def _parse_exam_date(answer: str) -> Optional[str]:
    a = (answer or "").strip().lower()
    if not a:
        return None
    if a in {"unknown", "idk", "no idea", "skip", "don't know", "dont know", "not sure"}:
        return "unknown"
    # ISO
    try:
        d = date.fromisoformat(a)
        return d.isoformat()
    except ValueError:
        pass
    # Try a few common formats
    for fmt in ("%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            d = datetime.strptime(answer.strip(), fmt).date()
            return d.isoformat()
        except ValueError:
            continue
    # Try dateutil if present (optional dep)
    try:
        from dateutil import parser as du
        d = du.parse(answer, default=datetime(date.today().year, 1, 1)).date()
        return d.isoformat()
    except Exception:
        return None


_CONFIRM_YES = {"yes", "y", "yep", "yeah", "confirm", "looks good", "go", "save"}
_CONFIRM_NO = {"no", "n", "nope", "redo", "start over", "restart"}


def _parse_confirm(answer: str) -> tuple[str, Optional[str]]:
    """Return (action, target). action ∈ {yes, no, change, unknown}, target = field for change."""
    a = (answer or "").strip().lower()
    if not a:
        return ("unknown", None)
    if a in _CONFIRM_YES:
        return ("yes", None)
    if a in _CONFIRM_NO:
        return ("no", None)
    m = re.match(r"change\s+(subjects?|topics?|exams?|exam dates?|hours|time)$", a)
    if m:
        target = m.group(1)
        norm = {"subject": "subjects", "subjects": "subjects",
                "topic": "topics", "topics": "topics",
                "exam": "exams", "exams": "exams", "exam date": "exams", "exam dates": "exams",
                "hours": "hours",
                "time": "time"}.get(target, target)
        return ("change", norm)
    return ("unknown", None)


# ── intake step engine ──────────────────────────────────────────────────────
def _next_prompt(st: IntakeState) -> str:
    if st.stage == "subjects":
        return "What subjects are you studying? List them comma-separated."
    if st.stage == "topics":
        s = st.subjects[st.cursor]
        return f"What topics are under {s}? List as many as you want, comma-separated."
    if st.stage == "exams":
        s = st.subjects[st.cursor]
        return f"When is the exam for {s}? Say a date like 2026-04-25, or say 'unknown' if you don't know yet."
    if st.stage == "hours":
        return "How many hours per day can you realistically study?"
    if st.stage == "time":
        return "What time of day works best for study — morning, afternoon, evening, or mixed?"
    if st.stage == "confirm":
        return _confirmation_text(st)
    return "All set."


def _confirmation_text(st: IntakeState) -> str:
    parts = [f"Here's the plan: {len(st.subjects)} subject{'s' if len(st.subjects)!=1 else ''}."]
    for s in st.subjects:
        topics = st.topics_by_subject.get(s, [])
        exam = st.exam_dates.get(s, "unknown")
        parts.append(f"{s}: {len(topics)} topics, exam {exam}.")
    parts.append(f"Budget: {st.hours_per_day} hours per day, preferred time {st.preferred_time}.")
    parts.append("Say 'yes' to save, 'no' to redo, or 'change subjects/topics/exams/hours/time' to edit one section.")
    return " ".join(parts)


async def start_intake(session_id: str) -> dict:
    _drop_stale()
    st = IntakeState(session_id=session_id)
    _intake_state[session_id] = st
    st.touch()
    return {"stage": st.stage, "prompt": _next_prompt(st), "complete": False}


async def advance_intake(session_id: str, answer: str) -> dict:
    _drop_stale()
    st = _intake_state.get(session_id)
    if not st:
        return await start_intake(session_id)
    st.touch()

    if st.stage == "subjects":
        subs = _split_list(answer)
        if not subs:
            return {"stage": st.stage, "prompt": "I didn't catch any subjects. Try again — comma-separated list.", "complete": False}
        st.subjects = subs
        st.cursor = 0
        st.stage = "topics"

    elif st.stage == "topics":
        topics = _split_list(answer)
        if not topics:
            return {"stage": st.stage, "prompt": f"I didn't catch any topics for {st.subjects[st.cursor]}. Try again.", "complete": False}
        st.topics_by_subject[st.subjects[st.cursor]] = topics
        st.cursor += 1
        if st.cursor >= len(st.subjects):
            st.cursor = 0
            st.stage = "exams"

    elif st.stage == "exams":
        parsed = _parse_exam_date(answer)
        if parsed is None:
            return {"stage": st.stage, "prompt": f"I couldn't parse that date for {st.subjects[st.cursor]}. Use YYYY-MM-DD or say 'unknown'.", "complete": False}
        st.exam_dates[st.subjects[st.cursor]] = parsed
        st.cursor += 1
        if st.cursor >= len(st.subjects):
            st.stage = "hours"

    elif st.stage == "hours":
        h = _parse_hours(answer)
        if h is None:
            return {"stage": st.stage, "prompt": "I need a number between 1 and 16. How many hours per day?", "complete": False}
        st.hours_per_day = h
        st.stage = "time"

    elif st.stage == "time":
        t = _parse_preferred_time(answer)
        if t is None:
            return {"stage": st.stage, "prompt": "Pick one — morning, afternoon, evening, or mixed.", "complete": False}
        st.preferred_time = t
        st.stage = "confirm"

    elif st.stage == "confirm":
        action, target = _parse_confirm(answer)
        if action == "yes":
            await _commit_intake(st)
            _intake_state.pop(session_id, None)
            return {"stage": "done", "prompt": "Saved. Your study plan is in Notion. Ask me 'what am I studying today' to get a daily plan.", "complete": True}
        if action == "no":
            _intake_state[session_id] = IntakeState(session_id=session_id)
            return {"stage": "subjects", "prompt": _next_prompt(_intake_state[session_id]), "complete": False}
        if action == "change":
            if target == "subjects":
                st.subjects = []
                st.topics_by_subject = {}
                st.exam_dates = {}
                st.cursor = 0
                st.stage = "subjects"
            elif target == "topics":
                st.topics_by_subject = {}
                st.cursor = 0
                st.stage = "topics"
            elif target == "exams":
                st.exam_dates = {}
                st.cursor = 0
                st.stage = "exams"
            elif target == "hours":
                st.hours_per_day = None
                st.stage = "hours"
            elif target == "time":
                st.preferred_time = None
                st.stage = "time"
        else:
            return {"stage": st.stage, "prompt": "Say 'yes' to save, 'no' to redo, or 'change subjects/topics/exams/hours/time'.", "complete": False}

    return {"stage": st.stage, "prompt": _next_prompt(st), "complete": False}


async def _commit_intake(st: IntakeState) -> None:
    plan = {
        "subjects": [
            {
                "name": s,
                "exam_date": st.exam_dates.get(s, "unknown"),
                "topics": [{"name": t, "done": False} for t in st.topics_by_subject.get(s, [])],
            }
            for s in st.subjects
        ],
        "hours_per_day": st.hours_per_day or 0,
        "preferred_time": st.preferred_time or "mixed",
    }
    await spn.write_intake(plan)
    logger.info(f"[StudyPlanner] Intake committed for {st.session_id[:8]}")


# ── public spec API ─────────────────────────────────────────────────────────
async def run_intake(session_id: str, mode: str = "text") -> dict:
    """Entrypoint — start or continue intake. Returns the next prompt + state."""
    if has_active_intake(session_id):
        # Caller is expected to use advance_intake on subsequent turns.
        st = _intake_state[session_id]
        return {"stage": st.stage, "prompt": _next_prompt(st), "complete": False}
    return await start_intake(session_id)


async def get_today_plan(session_id: str) -> dict:
    """Read or generate today's sub-page; return the plan dict + spoken summary."""
    today_iso = date.today().isoformat()
    existing = await spn.read_today_plan(today_iso)
    if existing:
        return {"date": today_iso, "plan": existing, "generated": False, "summary": _summarize_day(existing, today_iso)}

    study_plan = await spn.read_study_plan()
    if not study_plan.get("subjects"):
        return {"date": today_iso, "plan": None, "generated": False,
                "summary": "I don't have a study plan yet. Say 'plan my study' to set one up."}

    fresh = generate_today_plan(study_plan, date.today())
    day_plan = {
        "status": "planned",
        "total_minutes": fresh.get("total_minutes", 0),
        "subjects": fresh.get("subjects", []),
    }
    await spn.write_today_plan(today_iso, day_plan)
    return {"date": today_iso, "plan": day_plan, "generated": True, "summary": _summarize_day(day_plan, today_iso)}


def _summarize_day(day: dict, date_iso: str) -> str:
    if not day.get("subjects"):
        return f"No subjects scheduled for {date_iso}."
    parts = [f"Today, {date_iso}: {day.get('total_minutes', 0)} minutes total."]
    for s in day["subjects"]:
        topics = ", ".join(t["name"] if isinstance(t, dict) else str(t) for t in s.get("topics", []))
        parts.append(f"{s['name']} for {s.get('minutes', 0)} minutes — {topics}.")
    parts.append(f"Status: {day.get('status', 'planned')}.")
    return " ".join(parts)


async def mark_topic_done(session_id: str, subject: str, topic: str) -> dict:
    changed = await spn.mark_topic_done_in_notion(subject, topic)
    if changed:
        return {"ok": True, "summary": f"Marked '{topic}' done under {subject}."}
    return {"ok": False, "summary": f"I couldn't find '{topic}' under {subject}, or it's already done."}


async def update_daily_status(session_id: str, status: str) -> dict:
    valid = {"planned", "in-progress", "done", "skipped"}
    s = (status or "").strip().lower()
    if s not in valid:
        return {"ok": False, "summary": f"Status must be one of {sorted(valid)}."}
    today_iso = date.today().isoformat()
    existing = await spn.read_today_plan(today_iso)
    if not existing:
        return {"ok": False, "summary": "No daily plan exists for today yet."}
    existing["status"] = s
    await spn.write_today_plan(today_iso, existing)
    return {"ok": True, "summary": f"Today's status set to {s}."}


# ── CLI harness ─────────────────────────────────────────────────────────────
async def _cli_intake():
    sid = f"cli-{uuid.uuid4().hex[:8]}"
    print(f"[CLI] Session {sid}")
    res = await start_intake(sid)
    print(f"ASTA: {res['prompt']}")
    while not res["complete"]:
        try:
            answer = input("You: ").strip()
        except EOFError:
            break
        if not answer:
            continue
        res = await advance_intake(sid, answer)
        print(f"ASTA: {res['prompt']}")


async def _cli_today():
    sid = f"cli-{uuid.uuid4().hex[:8]}"
    res = await get_today_plan(sid)
    print(f"ASTA: {res['summary']}")
    if res.get("generated"):
        print("[CLI] Daily plan was just generated and saved to Notion.")
    elif res.get("plan"):
        print("[CLI] Daily plan was already in Notion.")


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="text", choices=["text", "voice"])
    parser.add_argument("--action", required=True, choices=["intake", "today"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.action == "intake":
        asyncio.run(_cli_intake())
    else:
        asyncio.run(_cli_today())


if __name__ == "__main__":
    main()
