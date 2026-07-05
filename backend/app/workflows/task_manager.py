"""
ASTA conversational task manager.

Implements the chat-driven routine task CRUD: create (with multi-turn
clarification), list, complete, reschedule — backed by the real Routine DB
(Task Name=title, Type=select, Scheduled Time=rich_text, Status=select, Date=date).

These run INSIDE the supervisor graph's `routine_workflow` node, so any
`interrupt()` here is bound to the checkpointed thread (thread_id = session_id)
and resumes correctly on the user's next message via Command(resume=...).
"""
import logging
import re
import functools
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz
from dateutil import parser as dtparser
from langgraph.types import interrupt

from backend.app.core.llm_factory import acomplete
from backend.app.services.notion_service import notion_service

logger = logging.getLogger("TaskManager")

IST = ZoneInfo("Asia/Kolkata")

ASTA_VOICE = (
    "You are ASTA, Karthik's personal AI assistant. Warm, sharp, concise. "
    "Call him 'boss'. Reply in natural language, never JSON."
)

# Fuzzy-match thresholds for matching a spoken task name to a Notion row.
_MATCH_MIN = 60      # below this = no match
_MATCH_GAP = 20      # top must beat runner-up by this much to be unambiguous

# create_task stores titles like "[MEDIUM] Call mom"; strip that prefix so the
# priority tag doesn't pollute fuzzy matching or what we show the user.
_PRIO_PREFIX = re.compile(r"^\s*\[(?:HIGH|MEDIUM|LOW)\]\s*", re.IGNORECASE)


def _clean_name(name: str) -> str:
    return _PRIO_PREFIX.sub("", name or "").strip()


# ── Action classification ─────────────────────────────────────────────────────

def classify_action(text: str) -> str:
    """Keyword-first routing of a routine task message. Order matters."""
    low = text.lower()
    if any(k in low for k in ["mark", "done", "completed", "finished", "complete", "tick off", "check off"]):
        return "complete"
    if any(k in low for k in ["move", "reschedule", "postpone", "push", "shift", "change the time"]):
        return "reschedule"
    if any(k in low for k in ["what's on", "whats on", "my list", "my plan", "what's my", "whats my",
                              "show me", "list my", "what do i have", "agenda", "my tasks", "my day"]):
        return "list"
    if any(k in low for k in ["remind", "add", "create", "schedule", "set a", "new task", "meeting", "meet", "attend"]):
        return "create"
    return "list"  # safe default: show what's planned


# ── LLM extraction helpers ─────────────────────────────────────────────────────

_RELATIVE_TIME_RE = re.compile(
    r'^\s*(?:in\s+)?(\d+)\s*(hour|hr|minute|min|second|sec)s?\s*$', re.IGNORECASE
)
_UNIT_SECONDS = {"hour": 3600, "hr": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}


def _normalize_time_phrase(time_str: str) -> str:
    """Convert a relative duration ("in 5 minutes", "2 hours") to an absolute
    HH:MM (IST) string, since _parse_reminder_datetime only understands
    absolute times. Absolute phrases ("5pm", "17:00") pass through unchanged."""
    if not time_str:
        return time_str
    m = _RELATIVE_TIME_RE.match(time_str.strip())
    if not m:
        return time_str
    amount, unit = int(m.group(1)), m.group(2).lower()
    target = datetime.now(IST) + timedelta(seconds=amount * _UNIT_SECONDS[unit])
    return target.strftime("%H:%M")


async def _extract_task(user_input: str) -> dict:
    """Pull task name / time / priority out of a create request."""
    raw = await acomplete(
        system="You extract a task name, time, and priority from a request. Be terse.",
        user=(
            f'Extract task details from: "{user_input}"\n\n'
            "Return EXACTLY:\n"
            "Task Name: [clear task description, no time words]\n"
            'Time: [time if mentioned e.g. "5pm", else "Not specified"]\n'
            "Priority: [high, medium, or low — default medium]"
        ),
        task="quick", temperature=0.0, max_tokens=80,
    )
    task_name, scheduled_time, priority = user_input, "", "medium"
    for line in (raw or "").splitlines():
        if line.startswith("Task Name:"):
            task_name = line.split(":", 1)[1].strip() or task_name
        elif line.startswith("Time:"):
            t = line.split(":", 1)[1].strip()
            if t and t.lower() != "not specified":
                scheduled_time = t
        elif line.startswith("Priority:"):
            p = line.split(":", 1)[1].strip().lower()
            if p in ("high", "medium", "low"):
                priority = p
    return {"task": task_name, "time": _normalize_time_phrase(scheduled_time), "priority": priority}


async def _extract_target_and_time(user_input: str) -> dict:
    """Pull target task name + new time out of a reschedule request."""
    raw = await acomplete(
        system="You extract which task to reschedule and the new time. Be terse.",
        user=(
            f'From: "{user_input}"\n\n'
            "Return EXACTLY:\n"
            "Target: [the task name being moved, no time words]\n"
            'Time: [the new time e.g. "7pm", else "Not specified"]'
        ),
        task="quick", temperature=0.0, max_tokens=60,
    )
    target, new_time = user_input, ""
    for line in (raw or "").splitlines():
        if line.startswith("Target:"):
            target = line.split(":", 1)[1].strip() or target
        elif line.startswith("Time:"):
            t = line.split(":", 1)[1].strip()
            if t and t.lower() != "not specified":
                new_time = t
    return {"target": target, "time": new_time}


# ── Fuzzy matching ─────────────────────────────────────────────────────────────

def _rank_matches(query: str, tasks: list) -> list:
    """Return tasks scored against query, descending, filtered to >= _MATCH_MIN."""
    q = _clean_name(query).lower()
    scored = [(t, fuzz.WRatio(q, _clean_name(t.get("task_name")).lower())) for t in tasks]
    scored.sort(key=lambda x: -x[1])
    return [(t, s) for t, s in scored if s >= _MATCH_MIN]


def _resolve_one(query: str, tasks: list):
    """Return (task, None) if a single confident match, (None, candidates) if ambiguous, (None, []) if none."""
    ranked = _rank_matches(query, tasks)
    if not ranked:
        return None, []
    if len(ranked) == 1:
        return ranked[0][0], None
    if ranked[0][1] - ranked[1][1] >= _MATCH_GAP:
        return ranked[0][0], None
    return None, [t for t, _ in ranked]


# ── Reminder scheduling ─────────────────────────────────────────────────────────

def _parse_reminder_datetime(task_date: str, scheduled_time: str):
    """Parse a Notion 'Date' (YYYY-MM-DD) + 'Scheduled Time' (e.g. '5pm') into an
    IST-aware datetime. Returns None if scheduled_time can't be parsed."""
    if not scheduled_time:
        return None
    try:
        base = datetime.fromisoformat(task_date)
        parsed = dtparser.parse(scheduled_time, default=base)
        return parsed.replace(tzinfo=IST)
    except (ValueError, OverflowError):
        logger.warning(f"[task_manager] couldn't parse reminder time {scheduled_time!r} on {task_date!r}")
        return None


async def _send_fcm_push(title: str, body: str):
    """Fire an FCM push to all registered device tokens.

    Gracefully skipped when service-account.json is absent or firebase-admin is
    not installed — callers never need to handle the failure.
    """
    try:
        import os
        sa_path = os.path.join(os.path.dirname(__file__), "..", "..", "secrets", "service-account.json")
        if not os.path.exists(sa_path):
            logger.info("[FCM] service-account.json not found — push skipped (place file to enable)")
            return

        import firebase_admin
        from firebase_admin import credentials, messaging

        if not firebase_admin._apps:
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)

        # Fetch all stored device tokens from Mongo.
        from backend.app.db.database import db_manager
        db = db_manager.db
        tokens = [doc["token"] async for doc in db["device_tokens"].find({}, {"token": 1})]

        if not tokens:
            logger.info("[FCM] no device tokens registered — push skipped")
            return

        # FCM multicast (up to 500 tokens per call).
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            tokens=tokens,
        )
        resp = messaging.send_each_for_multicast(message)
        logger.info(f"[FCM] sent to {resp.success_count}/{len(tokens)} devices")
    except Exception as e:
        logger.warning(f"[FCM] push failed (non-fatal): {e}")


async def _fire_reminder(page_id: str, task_name: str, scheduled_time: str):
    """APScheduler callback: broadcast a proactive reminder over WS, persist to
    Notion, and send an FCM push (gracefully skipped if not configured)."""
    from backend.app.api.ws_transport import broadcast_message, synthesize_proactive_audio_b64

    name = _clean_name(task_name)
    text = f"Boss — {name} — it's {scheduled_time}."
    audio_b64 = await synthesize_proactive_audio_b64(text)
    try:
        payload = {
            "type": "asta_proactive",
            "trigger": "reminder",
            "response": text,
            "page_id": page_id,
        }
        if audio_b64:
            payload["audio_base64"] = audio_b64
        await broadcast_message(payload)
    except Exception as e:
        logger.error(f"[task_manager] reminder broadcast failed for {page_id}: {e}")

    # Persist fired status to Notion instantly (visible even with no WS client).
    try:
        await notion_service.update_task_status(page_id, "Reminded")
    except Exception as e:
        logger.error(f"[task_manager] reminder status update failed for {page_id}: {e}")

    # FCM push — non-blocking, gracefully skipped when not configured.
    await _send_fcm_push(title="ASTA Reminder", body=text)


def _schedule_reminder(page_id: str, task_name: str, scheduled_time: str, task_date: str) -> bool:
    """Register a one-time APScheduler job to fire this reminder. Returns True if scheduled."""
    from backend.app.services.scheduler_service import scheduler_service

    run_at = _parse_reminder_datetime(task_date, scheduled_time)
    if run_at is None:
        return False
    if run_at <= datetime.now(IST):
        logger.info(f"[task_manager] reminder time {run_at} already past — not scheduling {page_id}")
        return False

    return scheduler_service.add_one_time_reminder(
        reminder_id=f"reminder-{page_id}",
        run_at=run_at,
        callback=functools.partial(_fire_reminder, page_id, task_name, scheduled_time),
    )


# ── Action handlers ─────────────────────────────────────────────────────────────

async def _handle_create(user_input: str, today: str) -> dict:
    extracted = await _extract_task(user_input)
    task, scheduled_time, priority = extracted["task"], extracted["time"], extracted["priority"]

    # Required field: time. Missing → pause and ask, hold context on the thread.
    if not scheduled_time:
        reply = interrupt({"question": f"What time should I set for '{task}', boss?", "field": "time"})
        scheduled_time = (reply or "").strip()

    page_id = await notion_service.create_task(
        task=task, time=scheduled_time, priority=priority, task_date=today,
    )
    if page_id:
        try:
            _schedule_reminder(page_id, task, scheduled_time, today)
        except Exception as e:
            logger.error(f"[task_manager] failed to schedule reminder for {page_id}: {e}")
    resp = await acomplete(
        ASTA_VOICE,
        f"Confirm you just added the task '{task}' at {scheduled_time} (priority {priority}) "
        f"to his Notion routine. One short friendly line, max 30 words.",
        task="quick", max_tokens=60,
    )
    return {"response": resp, "task_data": {"task": task, "time": scheduled_time, "priority": priority},
            "notion_page_id": page_id}


async def _handle_list(today: str) -> dict:
    tasks = await notion_service.get_pending_tasks(today)
    if not tasks:
        return {"response": "Nothing on your list for today, boss — clean slate. 🎯", "task_data": {"tasks": []}}
    listing = "\n".join(
        f"- {t['task_name']}" + (f" at {t['scheduled_time']}" if t.get("scheduled_time") else "")
        + f" [{t.get('status', 'Pending')}]"
        for t in tasks
    )
    resp = await acomplete(
        ASTA_VOICE,
        f"These are Karthik's tasks for today. Present them as a friendly natural-language rundown "
        f"(keep the times). Max 120 words.\n\n{listing}",
        task="quick", max_tokens=220,
    )
    return {"response": resp, "task_data": {"tasks": tasks}}


async def _handle_complete(user_input: str, today: str) -> dict:
    tasks = await notion_service.get_pending_tasks(today)
    if not tasks:
        return {"response": "You've got no open tasks today, boss — nothing to tick off.", "task_data": {}}

    target = await _extract_target_name_for_complete(user_input)
    match, candidates = _resolve_one(target, tasks)
    if match is None and candidates:
        names = ", ".join(_clean_name(c["task_name"]) for c in candidates)
        reply = interrupt({"question": f"Which one do you mean, boss — {names}?", "field": "which_task"})
        match, candidates = _resolve_one((reply or "").strip(), tasks)
    if match is None:
        return {"response": f"I couldn't find an open task matching '{target}', boss.", "task_data": {}}

    name = _clean_name(match["task_name"])
    ok = await notion_service.update_task_status(match["page_id"], "Completed")
    if not ok:
        return {"response": f"I found '{name}' but couldn't update it, boss.", "task_data": {}}
    return {"response": f"Done, boss — marked '{name}' as completed. ✅",
            "task_data": {"completed": name}}


async def _handle_reschedule(user_input: str, today: str) -> dict:
    tasks = await notion_service.get_pending_tasks(today)
    if not tasks:
        return {"response": "No tasks to move today, boss.", "task_data": {}}

    parsed = await _extract_target_and_time(user_input)
    target, new_time = parsed["target"], parsed["time"]

    match, candidates = _resolve_one(target, tasks)
    if match is None and candidates:
        names = ", ".join(_clean_name(c["task_name"]) for c in candidates)
        reply = interrupt({"question": f"Which task should I move, boss — {names}?", "field": "which_task"})
        match, candidates = _resolve_one((reply or "").strip(), tasks)
    if match is None:
        return {"response": f"I couldn't find a task matching '{target}' to move, boss.", "task_data": {}}

    name = _clean_name(match["task_name"])
    if not new_time:
        reply = interrupt({"question": f"What time should I move '{name}' to, boss?", "field": "time"})
        new_time = (reply or "").strip()

    ok = await notion_service.update_task_schedule(match["page_id"], scheduled_time=new_time)
    if not ok:
        return {"response": f"I found '{name}' but couldn't reschedule it, boss.", "task_data": {}}
    return {"response": f"Moved '{name}' to {new_time}, boss. ⏰",
            "task_data": {"rescheduled": name, "time": new_time}}


async def _extract_target_name_for_complete(user_input: str) -> str:
    """Strip command words from a 'mark X as done' phrase to get the task name."""
    raw = await acomplete(
        system="Extract only the task name the user wants to mark done. Reply with just the name.",
        user=f'From: "{user_input}"\nTask name only:',
        task="quick", temperature=0.0, max_tokens=30,
    )
    name = (raw or "").strip().strip('"').splitlines()[0] if raw else user_input
    return name or user_input


# ── Entry point ─────────────────────────────────────────────────────────────────

async def handle_routine_turn(user_input: str) -> dict:
    """Route a chat routine message to create / list / complete / reschedule.

    May raise GraphInterrupt (via interrupt()) — the caller must let it propagate.
    """
    today = date.today().isoformat()
    action = classify_action(user_input)
    logger.info(f"[task_manager] action={action} input={user_input[:50]!r}")
    if action == "create":
        return await _handle_create(user_input, today)
    if action == "complete":
        return await _handle_complete(user_input, today)
    if action == "reschedule":
        return await _handle_reschedule(user_input, today)
    return await _handle_list(today)
