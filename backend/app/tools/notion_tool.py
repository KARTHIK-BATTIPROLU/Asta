"""
NotionTool - Full CRUD for Karthik's Notion workspace.

Operations: create_page, append_to_page, read_page, query_database, update_page, search
Provider: Notion API (NOTION_API_KEY env var)
Databases: research, developer, content, youtube, routine
"""

import asyncio
import logging
import os
import re
from typing import Optional

import httpx

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("NotionTool")

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
TIMEOUT = 10.0
MAX_RETRIES = 3

VALID_OPERATIONS = {"create_page", "append_to_page", "read_page", "query_database", "update_page", "search", "clear_page"}


def _api_key() -> str:
    return os.getenv("NOTION_API_KEY", "")


def _db_map() -> dict:
    return {
        "research": os.getenv("NOTION_RESEARCH_DB", ""),
        "developer": os.getenv("NOTION_DEVELOPER_DB", ""),
        "content": os.getenv("NOTION_CONTENT_DB", ""),
        "youtube": os.getenv("NOTION_YOUTUBE_DB", ""),
        "routine": os.getenv("NOTION_ROUTINE_DB", ""),
    }


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _markdown_to_blocks(markdown: str) -> list[dict]:
    """Convert markdown text to Notion block objects."""
    blocks = []
    lines = markdown.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Headings
        if stripped.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]},
            })
        elif stripped.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]},
            })
        elif stripped.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]},
            })
        # Bullet list
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]},
            })
        # Numbered list
        elif re.match(r'^\d+\.\s', stripped):
            text = re.sub(r'^\d+\.\s', '', stripped)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]},
            })
        # Todo
        elif stripped.startswith("[ ] "):
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[4:]}}],
                    "checked": False,
                },
            })
        elif stripped.startswith("[x] "):
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[4:]}}],
                    "checked": True,
                },
            })
        # Default: paragraph
        else:
            # Notion caps rich_text at 2000 chars per block
            for chunk in [stripped[i:i+2000] for i in range(0, len(stripped), 2000)]:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
                })

    return blocks


def _blocks_to_text(blocks: list[dict]) -> str:
    """Convert Notion blocks back to clean plain text."""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        container = block.get(btype, {})
        rich_text = container.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text)

        if btype == "heading_1":
            lines.append(f"# {text}")
        elif btype == "heading_2":
            lines.append(f"## {text}")
        elif btype == "heading_3":
            lines.append(f"### {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "to_do":
            checked = container.get("checked", False)
            lines.append(f"[{'x' if checked else ' '}] {text}")
        elif text:
            lines.append(text)

    return "\n".join(lines)


class NotionTool(BaseTool):
    name = "notion"
    description = "Full CRUD for Karthik's Notion workspace: create, read, update, query, and search across all databases."

    async def validate(self, payload: dict) -> tuple[bool, str]:
        operation = payload.get("operation", "")
        if operation not in VALID_OPERATIONS:
            return False, f"Invalid operation '{operation}'. Must be one of: {VALID_OPERATIONS}"

        if not _api_key():
            return False, "NOTION_API_KEY not configured in environment"

        db_map = _db_map()
        # Operation-specific validation
        if operation == "create_page":
            db = payload.get("database", "")
            if db and db not in db_map:
                return False, f"Unknown database '{db}'. Valid: {list(db_map.keys())}"
            if not payload.get("properties") and not payload.get("content"):
                return False, "create_page requires 'properties' or 'content'"

        elif operation in ("append_to_page", "read_page", "update_page", "clear_page"):
            if not payload.get("page_id"):
                return False, f"'{operation}' requires 'page_id'"

        elif operation == "query_database":
            db = payload.get("database", "")
            if not db or db not in db_map:
                return False, f"query_database requires valid 'database'. Valid: {list(db_map.keys())}"

        elif operation == "search":
            if not payload.get("query"):
                return False, "search requires 'query'"

        return True, ""

    async def execute(self, payload: dict) -> dict:
        operation = payload["operation"]

        if operation == "create_page":
            return await self._create_page(payload)
        elif operation == "append_to_page":
            return await self._append_to_page(payload)
        elif operation == "read_page":
            return await self._read_page(payload)
        elif operation == "query_database":
            return await self._query_database(payload)
        elif operation == "update_page":
            return await self._update_page(payload)
        elif operation == "search":
            return await self._search(payload)
        elif operation == "clear_page":
            return await self._clear_page(payload)
        else:
            return {"error": f"Unknown operation: {operation}"}

    async def _create_page(self, payload: dict) -> dict:
        db_name = payload.get("database", "research")
        db_id = _db_map().get(db_name, payload.get("database_id", ""))
        properties = payload.get("properties", {})
        content = payload.get("content", "")
        title_property = payload.get("title_property", "Name")

        # Build default title property if caller didn't already supply it
        if title_property not in properties and "title" not in properties:
            title = payload.get("title", content[:50] if content else "Untitled")
            properties[title_property] = {"title": [{"text": {"content": title}}]}

        body = {
            "parent": {"database_id": db_id},
            "properties": properties,
        }

        if content:
            body["children"] = _markdown_to_blocks(content)

        data = await self._api("POST", "/pages", body)
        if "error" in data:
            return data

        return {
            "data": {
                "page_id": data.get("id", ""),
                "url": data.get("url", ""),
                "database": db_name,
            },
            "message": f"Page created in {db_name}: {data.get('url', '')}",
        }

    async def _append_to_page(self, payload: dict) -> dict:
        page_id = payload["page_id"]
        content = payload.get("content", "")
        if not content:
            return {"error": "No content to append"}

        blocks = _markdown_to_blocks(content)
        body = {"children": blocks}

        data = await self._api("PATCH", f"/blocks/{page_id}/children", body)
        if "error" in data:
            return data

        return {
            "data": {"page_id": page_id, "blocks_added": len(blocks)},
            "message": f"Appended {len(blocks)} blocks to page {page_id[:8]}",
        }

    async def _read_page(self, payload: dict) -> dict:
        page_id = payload["page_id"]

        # Fetch blocks
        data = await self._api("GET", f"/blocks/{page_id}/children")
        if "error" in data:
            return data

        blocks = data.get("results", [])
        text = _blocks_to_text(blocks)

        return {
            "data": {"page_id": page_id, "content": text, "block_count": len(blocks)},
            "message": f"Read {len(blocks)} blocks from page {page_id[:8]}",
        }

    async def _query_database(self, payload: dict) -> dict:
        db_name = payload["database"]
        db_id = _db_map()[db_name]
        filters = payload.get("filters", {})

        body = {}
        if filters:
            body["filter"] = filters

        data = await self._api("POST", f"/databases/{db_id}/query", body)
        if "error" in data:
            return data

        results = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            title = ""
            for key, val in props.items():
                if val.get("type") == "title":
                    title_parts = val.get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                    break

            results.append({
                "page_id": page.get("id", ""),
                "title": title,
                "url": page.get("url", ""),
                "created": page.get("created_time", ""),
                "last_edited": page.get("last_edited_time", ""),
            })

        return {
            "data": {"database": db_name, "pages": results, "count": len(results)},
            "message": f"Found {len(results)} pages in {db_name}",
        }

    async def _update_page(self, payload: dict) -> dict:
        page_id = payload["page_id"]
        properties = payload.get("properties", {})

        if not properties:
            return {"error": "No properties to update"}

        body = {"properties": properties}
        data = await self._api("PATCH", f"/pages/{page_id}", body)
        if "error" in data:
            return data

        return {
            "data": {"page_id": page_id, "updated_properties": list(properties.keys())},
            "message": f"Updated properties on page {page_id[:8]}",
        }

    async def _search(self, payload: dict) -> dict:
        query = payload["query"]
        body = {"query": query, "page_size": 10}

        data = await self._api("POST", "/search", body)
        if "error" in data:
            return data

        results = []
        for item in data.get("results", []):
            props = item.get("properties", {})
            title = ""
            for key, val in props.items():
                if val.get("type") == "title":
                    title_parts = val.get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                    break

            results.append({
                "id": item.get("id", ""),
                "title": title or item.get("url", "untitled"),
                "url": item.get("url", ""),
                "type": item.get("object", ""),
            })

        return {
            "data": {"query": query, "results": results, "count": len(results)},
            "message": f"Found {len(results)} results for '{query}'",
        }

    async def _clear_page(self, payload: dict) -> dict:
        """Delete all child blocks of a page (idempotent rewrite primitive)."""
        page_id = payload["page_id"]
        list_data = await self._api("GET", f"/blocks/{page_id}/children")
        if "error" in list_data:
            return list_data

        deleted = 0
        for block in list_data.get("results", []):
            bid = block.get("id")
            if not bid:
                continue
            del_data = await self._api("DELETE", f"/blocks/{bid}")
            if "error" not in del_data:
                deleted += 1
        return {
            "data": {"page_id": page_id, "blocks_deleted": deleted},
            "message": f"Cleared {deleted} blocks from page {page_id[:8]}",
        }

    async def _api(self, method: str, endpoint: str, body: dict = None) -> dict:
        """Make an API call to Notion with retry on 429."""
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    url = f"{NOTION_BASE_URL}{endpoint}"
                    if method == "GET":
                        resp = await client.get(url, headers=_headers())
                    elif method == "POST":
                        resp = await client.post(url, json=body or {}, headers=_headers())
                    elif method == "PATCH":
                        resp = await client.patch(url, json=body or {}, headers=_headers())
                    elif method == "DELETE":
                        resp = await client.delete(url, headers=_headers())
                    else:
                        return {"error": f"Unsupported HTTP method: {method}"}

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(f"[Notion] Rate limited. Retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code >= 400:
                        error_data = resp.json() if resp.content else {}
                        error_msg = error_data.get("message", resp.text[:200])
                        return {"error": f"Notion API {resp.status_code}: {error_msg}"}

                    return resp.json()

            except httpx.TimeoutException:
                if attempt == MAX_RETRIES - 1:
                    return {"error": "Notion API timed out"}
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"Notion API failed: {e}"}
                await asyncio.sleep(2 ** attempt)

        return {"error": "Notion API failed after retries"}
