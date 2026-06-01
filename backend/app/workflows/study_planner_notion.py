"""
Notion wrapper for the Study Plan workflow.

All Notion access goes through the existing NotionTool — never raw httpx.
Single source of truth lives on one row in the Notion routine database,
titled "ASTA — Study Plan". Everything else lives as child blocks on that row.

Markdown layout rendered into the page (round-trips via NotionTool's converters):

    ## Subjects
    ### {subject}
    - exam: YYYY-MM-DD | unknown
    [ ] topic
    [x] topic

    ## Daily Budget
    - hours_per_day: N
    - preferred_time: morning|afternoon|evening|mixed

    ## Daily Plans
    ### YYYY-MM-DD
    - status: planned|in-progress|done|skipped
    - total_minutes: N
    - {subject}: M min
    [ ] topic
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from backend.app.tools.notion_tool import NotionTool

logger = logging.getLogger("StudyPlannerNotion")

PAGE_TITLE = "ASTA — Study Plan"
ROUTINE_DB = "routine"

_notion = NotionTool()


# ── low-level helper ────────────────────────────────────────────────────────
async def _call(payload: dict) -> dict:
    """Invoke NotionTool, raise on non-success, return result.data dict."""
    res = await _notion.run(payload)
    if res.get("status") != "success":
        raise RuntimeError(f"Notion {payload.get('operation')} failed: {res.get('error')}")
    return (res.get("result") or {}).get("data", {}) or {}


# ── markdown serialization ──────────────────────────────────────────────────
def _serialize(plan: dict) -> str:
    lines: list[str] = []

    lines.append("## Subjects")
    for s in plan.get("subjects", []) or []:
        name = s.get("name", "").strip()
        if not name:
            continue
        lines.append(f"### {name}")
        exam = s.get("exam_date") or "unknown"
        lines.append(f"- exam: {exam}")
        for t in s.get("topics", []) or []:
            tname = t.get("name") if isinstance(t, dict) else str(t)
            tname = (tname or "").strip()
            if not tname:
                continue
            done = bool(t.get("done", False)) if isinstance(t, dict) else False
            lines.append(f"[{'x' if done else ' '}] {tname}")
        lines.append("")

    lines.append("## Daily Budget")
    lines.append(f"- hours_per_day: {int(plan.get('hours_per_day') or 0)}")
    lines.append(f"- preferred_time: {plan.get('preferred_time') or 'mixed'}")
    lines.append("")

    lines.append("## Daily Plans")
    for day in plan.get("daily_plans", []) or []:
        lines.append(f"### {day.get('date', '')}")
        lines.append(f"- status: {day.get('status', 'planned')}")
        lines.append(f"- total_minutes: {int(day.get('total_minutes') or 0)}")
        for sb in day.get("subjects", []) or []:
            sname = sb.get("name", "")
            mins = int(sb.get("minutes") or 0)
            lines.append(f"- {sname}: {mins} min")
            for tp in sb.get("topics", []) or []:
                tname = tp if isinstance(tp, str) else tp.get("name", "")
                done = False if isinstance(tp, str) else bool(tp.get("done", False))
                lines.append(f"[{'x' if done else ' '}] {tname}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ── markdown parsing ────────────────────────────────────────────────────────
_TODO_RE = re.compile(r"^\[(x| )\]\s+(.+)$", re.IGNORECASE)
_SUBJECT_KV_RE = re.compile(r"^-\s*([a-z_]+)\s*:\s*(.+)$", re.IGNORECASE)
_DAILY_SUBJECT_RE = re.compile(r"^-\s*(.+?)\s*:\s*(\d+)\s*min$", re.IGNORECASE)


def _parse(markdown: str) -> dict:
    plan = {
        "subjects": [],
        "hours_per_day": 0,
        "preferred_time": "mixed",
        "daily_plans": [],
    }

    section: Optional[str] = None  # "subjects" | "budget" | "daily"
    cur_subject: Optional[dict] = None
    cur_day: Optional[dict] = None
    cur_day_subject: Optional[dict] = None

    def flush_subject():
        nonlocal cur_subject
        if cur_subject:
            plan["subjects"].append(cur_subject)
            cur_subject = None

    def flush_day():
        nonlocal cur_day, cur_day_subject
        if cur_day:
            plan["daily_plans"].append(cur_day)
        cur_day = None
        cur_day_subject = None

    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        if line.startswith("## "):
            heading = line[3:].strip().lower()
            flush_subject()
            flush_day()
            if heading.startswith("subject"):
                section = "subjects"
            elif heading.startswith("daily budget"):
                section = "budget"
            elif heading.startswith("daily plan"):
                section = "daily"
            else:
                section = None
            continue

        if line.startswith("### "):
            title = line[4:].strip()
            if section == "subjects":
                flush_subject()
                cur_subject = {"name": title, "exam_date": "unknown", "topics": []}
            elif section == "daily":
                flush_day()
                cur_day = {"date": title, "status": "planned", "total_minutes": 0, "subjects": []}
                cur_day_subject = None
            continue

        if section == "subjects" and cur_subject is not None:
            kv = _SUBJECT_KV_RE.match(line)
            if kv and kv.group(1).lower() == "exam":
                cur_subject["exam_date"] = kv.group(2).strip()
                continue
            todo = _TODO_RE.match(line)
            if todo:
                cur_subject["topics"].append({
                    "name": todo.group(2).strip(),
                    "done": todo.group(1).lower() == "x",
                })
                continue

        elif section == "budget":
            kv = _SUBJECT_KV_RE.match(line)
            if not kv:
                continue
            key = kv.group(1).lower()
            val = kv.group(2).strip()
            if key == "hours_per_day":
                try:
                    plan["hours_per_day"] = int(val)
                except ValueError:
                    pass
            elif key == "preferred_time":
                plan["preferred_time"] = val

        elif section == "daily" and cur_day is not None:
            kv = _SUBJECT_KV_RE.match(line)
            if kv and kv.group(1).lower() in ("status", "total_minutes"):
                key = kv.group(1).lower()
                val = kv.group(2).strip()
                if key == "status":
                    cur_day["status"] = val
                else:
                    try:
                        cur_day["total_minutes"] = int(val)
                    except ValueError:
                        pass
                continue
            ds = _DAILY_SUBJECT_RE.match(line)
            if ds:
                cur_day_subject = {"name": ds.group(1).strip(), "minutes": int(ds.group(2)), "topics": []}
                cur_day["subjects"].append(cur_day_subject)
                continue
            todo = _TODO_RE.match(line)
            if todo and cur_day_subject is not None:
                cur_day_subject["topics"].append({
                    "name": todo.group(2).strip(),
                    "done": todo.group(1).lower() == "x",
                })

    flush_subject()
    flush_day()
    return plan


# ── public API ──────────────────────────────────────────────────────────────
async def ensure_study_plan_page() -> str:
    """Return the page_id for ASTA — Study Plan, creating it if missing."""
    res = await _call({"operation": "query_database", "database": ROUTINE_DB})
    for p in res.get("pages", []) or []:
        if (p.get("title") or "").strip() == PAGE_TITLE:
            return p["page_id"]

    created = await _call({
        "operation": "create_page",
        "database": ROUTINE_DB,
        "title": PAGE_TITLE,
        "title_property": "Task Name",
        "content": "## Subjects\n\n## Daily Budget\n\n## Daily Plans\n",
    })
    return created["page_id"]


async def read_study_plan() -> dict:
    """Read the page and return the normalized study-plan dict."""
    page_id = await ensure_study_plan_page()
    res = await _call({"operation": "read_page", "page_id": page_id})
    return _parse(res.get("content", ""))


async def write_intake(plan: dict) -> None:
    """Idempotent upsert: clear page, then write the intake content fresh."""
    page_id = await ensure_study_plan_page()
    existing = await read_study_plan()
    merged = {
        "subjects": plan.get("subjects", existing.get("subjects", [])),
        "hours_per_day": plan.get("hours_per_day", existing.get("hours_per_day", 0)),
        "preferred_time": plan.get("preferred_time", existing.get("preferred_time", "mixed")),
        "daily_plans": existing.get("daily_plans", []),
    }
    await _call({"operation": "clear_page", "page_id": page_id})
    await _call({
        "operation": "append_to_page",
        "page_id": page_id,
        "content": _serialize(merged),
    })


async def read_today_plan(date: str) -> Optional[dict]:
    plan = await read_study_plan()
    for day in plan.get("daily_plans", []) or []:
        if day.get("date") == date:
            return day
    return None


async def write_today_plan(date: str, day_plan: dict) -> None:
    """Add or replace a daily plan entry. Page is rewritten (idempotent)."""
    plan = await read_study_plan()
    plan.setdefault("daily_plans", [])
    plan["daily_plans"] = [d for d in plan["daily_plans"] if d.get("date") != date]
    entry = dict(day_plan)
    entry["date"] = date
    plan["daily_plans"].append(entry)
    plan["daily_plans"].sort(key=lambda d: d.get("date", ""))

    page_id = await ensure_study_plan_page()
    await _call({"operation": "clear_page", "page_id": page_id})
    await _call({
        "operation": "append_to_page",
        "page_id": page_id,
        "content": _serialize(plan),
    })


async def mark_topic_done_in_notion(subject: str, topic: str) -> bool:
    """Flip [ ] -> [x] for the topic under the named subject. Returns True if changed."""
    plan = await read_study_plan()
    changed = False
    sn = subject.strip().lower()
    tn = topic.strip().lower()
    for s in plan.get("subjects", []) or []:
        if s.get("name", "").strip().lower() != sn:
            continue
        for t in s.get("topics", []) or []:
            if t.get("name", "").strip().lower() == tn and not t.get("done"):
                t["done"] = True
                changed = True
        break
    if not changed:
        return False

    page_id = await ensure_study_plan_page()
    await _call({"operation": "clear_page", "page_id": page_id})
    await _call({
        "operation": "append_to_page",
        "page_id": page_id,
        "content": _serialize(plan),
    })
    return True
