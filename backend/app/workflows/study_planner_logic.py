"""
Pure planner for ASTA Study Plan workflow.

generate_today_plan(study_plan, today) -> dict
No I/O, no side effects. Unit-testable.

Rules:
- Subjects with exam_date within 14 days get priority.
- Unknown / past exam dates get lowest priority.
- topics_today = min(nearest_exam_days * 2, hours_per_day); fallback hours_per_day when no known exam.
- At least 1 subject, at most 3.
- Only topics not yet marked done are scheduled.
"""

from __future__ import annotations

from datetime import date
from typing import Optional


def _parse_exam_date(value) -> Optional[date]:
    if not value or value == "unknown":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _remaining_topics(subject: dict) -> list[str]:
    out = []
    for t in subject.get("topics", []) or []:
        if isinstance(t, dict):
            if not t.get("done", False):
                name = t.get("name", "").strip()
                if name:
                    out.append(name)
        elif isinstance(t, str) and t.strip():
            out.append(t.strip())
    return out


def generate_today_plan(study_plan: dict, today: date) -> dict:
    subjects = (study_plan or {}).get("subjects", []) or []
    hours_per_day = int((study_plan or {}).get("hours_per_day") or 2)
    if hours_per_day < 1:
        hours_per_day = 1

    candidates = []
    for s in subjects:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        remaining = _remaining_topics(s)
        if not remaining:
            continue
        ed = _parse_exam_date(s.get("exam_date"))
        days_until: Optional[int] = None
        if ed is not None:
            delta = (ed - today).days
            days_until = delta if delta >= 0 else None  # past exams treated as unknown
        candidates.append({
            "name": name,
            "remaining": remaining,
            "days_until": days_until,
        })

    if not candidates:
        return {
            "date": today.isoformat(),
            "total_minutes": 0,
            "subjects": [],
            "note": "No subjects with remaining topics.",
        }

    # Priority: known days_until ascending, unknown last.
    candidates.sort(key=lambda c: (c["days_until"] is None, c["days_until"] if c["days_until"] is not None else 0))

    near = [c for c in candidates if c["days_until"] is not None and c["days_until"] <= 14]
    pool = near if near else candidates

    num_subjects = min(3, max(1, len(pool)))
    chosen = pool[:num_subjects]

    nearest = chosen[0]["days_until"]
    if nearest is not None and nearest > 0:
        total_topics_budget = min(nearest * 2, hours_per_day)
    else:
        total_topics_budget = hours_per_day
    total_topics_budget = max(1, total_topics_budget)

    per_subject_topics = max(1, total_topics_budget // len(chosen))
    per_subject_minutes = (hours_per_day * 60) // len(chosen)

    plan_subjects = []
    for c in chosen:
        topics = c["remaining"][:per_subject_topics]
        if not topics:
            continue
        plan_subjects.append({
            "name": c["name"],
            "minutes": per_subject_minutes,
            "topics": topics,
        })

    return {
        "date": today.isoformat(),
        "total_minutes": per_subject_minutes * len(plan_subjects),
        "subjects": plan_subjects,
    }
