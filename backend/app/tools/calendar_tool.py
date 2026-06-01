"""
CalendarTool â€” Google Calendar CRUD via Service Account.

Operations: get_today, get_week, create_event, update_event, delete_event, get_pending
Auth: Google Service Account via GOOGLE_SA_KEY_PATH
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("CalendarTool")

SA_KEY_PATH = os.getenv("GOOGLE_SA_KEY_PATH", "serviceAccountKey.json")
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEOUT = 10.0
MAX_RETRIES = 3


def _get_credentials():
    """Load Google Service Account credentials."""
    try:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            SA_KEY_PATH, scopes=CALENDAR_SCOPES
        )
        return creds
    except Exception as e:
        logger.error(f"[Calendar] Failed to load service account: {e}")
        return None


def _get_access_token() -> Optional[str]:
    """Get a fresh access token from the service account."""
    creds = _get_credentials()
    if not creds:
        return None
    try:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        logger.error(f"[Calendar] Token refresh failed: {e}")
        return None


def _relative_time(dt_str: str) -> str:
    """Convert ISO datetime string to relative human format."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = dt - now

        if diff.total_seconds() < 0:
            # In the past
            abs_diff = abs(diff)
            if abs_diff.total_seconds() < 3600:
                return f"{int(abs_diff.total_seconds() / 60)} minutes ago"
            elif abs_diff.total_seconds() < 86400:
                return f"{int(abs_diff.total_seconds() / 3600)} hours ago"
            else:
                return dt.strftime("%b %d at %I:%M %p")
        else:
            if diff.total_seconds() < 3600:
                return f"in {int(diff.total_seconds() / 60)} minutes"
            elif diff.total_seconds() < 86400:
                return f"in {int(diff.total_seconds() / 3600)} hours"
            elif diff.days == 1:
                return f"tomorrow at {dt.strftime('%I:%M %p')}"
            else:
                return dt.strftime("%A at %I:%M %p")
    except Exception:
        return dt_str


class CalendarTool(BaseTool):
    name = "calendar"
    description = "Google Calendar: view today/week, create/update/delete events, get pending tasks."

    # Target calendar â€” set to 'primary' or a specific calendar ID
    CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    async def validate(self, payload: dict) -> tuple[bool, str]:
        operation = payload.get("operation", "")
        valid_ops = {"get_today", "get_week", "create_event", "update_event", "delete_event", "get_pending"}
        if operation not in valid_ops:
            return False, f"Invalid operation '{operation}'. Must be one of: {valid_ops}"

        if not os.path.exists(SA_KEY_PATH):
            return False, f"Service account key not found at: {SA_KEY_PATH}"

        if operation == "create_event":
            if not payload.get("title"):
                return False, "create_event requires 'title'"
            if not payload.get("date"):
                return False, "create_event requires 'date' (YYYY-MM-DD)"

        if operation in ("update_event", "delete_event"):
            if not payload.get("event_id"):
                return False, f"'{operation}' requires 'event_id'"

        return True, ""

    async def execute(self, payload: dict) -> dict:
        operation = payload["operation"]

        token = await asyncio.to_thread(_get_access_token)
        if not token:
            return {"error": "Failed to authenticate with Google Calendar"}

        if operation == "get_today":
            return await self._get_events(token, days=1)
        elif operation == "get_week":
            return await self._get_events(token, days=7)
        elif operation == "create_event":
            return await self._create_event(token, payload)
        elif operation == "update_event":
            return await self._update_event(token, payload)
        elif operation == "delete_event":
            return await self._delete_event(token, payload)
        elif operation == "get_pending":
            return await self._get_events(token, days=30, pending_only=True)
        else:
            return {"error": f"Unknown operation: {operation}"}

    async def _get_events(self, token: str, days: int = 1, pending_only: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days)).isoformat()

        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        }

        data = await self._api("GET", f"/calendars/{self.CALENDAR_ID}/events", token, params=params)
        if "error" in data:
            return data

        events = []
        for item in data.get("items", []):
            start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date", ""))
            end = item.get("end", {}).get("dateTime", item.get("end", {}).get("date", ""))

            event = {
                "event_id": item.get("id", ""),
                "title": item.get("summary", "Untitled"),
                "start": start,
                "end": end,
                "relative_time": _relative_time(start),
                "description": item.get("description", ""),
                "status": item.get("status", ""),
            }
            events.append(event)

        label = "today's" if days == 1 else f"next {days} days'"
        return {
            "data": {"events": events, "count": len(events)},
            "message": f"{len(events)} events for {label} schedule",
        }

    async def _create_event(self, token: str, payload: dict) -> dict:
        title = payload["title"]
        date = payload["date"]
        time_str = payload.get("time", "09:00")
        duration = payload.get("duration_minutes", 60)
        description = payload.get("description", "")

        # Build datetime
        try:
            start_dt = datetime.fromisoformat(f"{date}T{time_str}:00")
            end_dt = start_dt + timedelta(minutes=duration)
        except ValueError as e:
            return {"error": f"Invalid date/time format: {e}"}

        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Amsterdam"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Amsterdam"},
        }

        data = await self._api("POST", f"/calendars/{self.CALENDAR_ID}/events", token, body=body)
        if "error" in data:
            return data

        return {
            "data": {
                "event_id": data.get("id", ""),
                "title": title,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "link": data.get("htmlLink", ""),
            },
            "message": f"Event created: '{title}' on {date} at {time_str}",
        }

    async def _update_event(self, token: str, payload: dict) -> dict:
        event_id = payload["event_id"]
        changes = payload.get("changes", {})

        body = {}
        if "title" in changes:
            body["summary"] = changes["title"]
        if "description" in changes:
            body["description"] = changes["description"]
        if "date" in changes and "time" in changes:
            start = datetime.fromisoformat(f"{changes['date']}T{changes['time']}:00")
            duration = changes.get("duration_minutes", 60)
            end = start + timedelta(minutes=duration)
            body["start"] = {"dateTime": start.isoformat(), "timeZone": "Europe/Amsterdam"}
            body["end"] = {"dateTime": end.isoformat(), "timeZone": "Europe/Amsterdam"}

        if not body:
            return {"error": "No valid changes provided"}

        data = await self._api("PATCH", f"/calendars/{self.CALENDAR_ID}/events/{event_id}", token, body=body)
        if "error" in data:
            return data

        return {
            "data": {"event_id": event_id, "updated_fields": list(body.keys())},
            "message": f"Event {event_id[:8]} updated: {list(body.keys())}",
        }

    async def _delete_event(self, token: str, payload: dict) -> dict:
        event_id = payload["event_id"]

        data = await self._api("DELETE", f"/calendars/{self.CALENDAR_ID}/events/{event_id}", token)
        if "error" in data:
            return data

        return {
            "data": {"event_id": event_id, "deleted": True},
            "message": f"Event {event_id[:8]} deleted",
        }

    async def _api(self, method: str, endpoint: str, token: str, params: dict = None, body: dict = None) -> dict:
        """Make Google Calendar API call with retry."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        base_url = "https://www.googleapis.com/calendar/v3"

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    url = f"{base_url}{endpoint}"

                    if method == "GET":
                        resp = await client.get(url, headers=headers, params=params)
                    elif method == "POST":
                        resp = await client.post(url, json=body or {}, headers=headers)
                    elif method == "PATCH":
                        resp = await client.patch(url, json=body or {}, headers=headers)
                    elif method == "DELETE":
                        resp = await client.delete(url, headers=headers)
                        if resp.status_code == 204:
                            return {"deleted": True}
                    else:
                        return {"error": f"Unsupported method: {method}"}

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(f"[Calendar] Rate limited. Retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code >= 400:
                        error_data = resp.json() if resp.content else {}
                        error_msg = error_data.get("error", {}).get("message", resp.text[:200])
                        return {"error": f"Calendar API {resp.status_code}: {error_msg}"}

                    return resp.json()

            except httpx.TimeoutException:
                if attempt == MAX_RETRIES - 1:
                    return {"error": "Calendar API timed out"}
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"Calendar API failed: {e}"}
                await asyncio.sleep(2 ** attempt)

        return {"error": "Calendar API failed after retries"}
