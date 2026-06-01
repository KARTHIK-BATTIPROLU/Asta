"""
ToolRegistry - Central router for all ASTA API tools.

Registers all tools on import, routes incoming OpenClaw payloads to the
correct tool by the "tool" field. Logs every call with correlation ID.

Usage:
    result = await tool_registry.route(payload)
    tools = await tool_registry.list_tools()
"""

import logging
import time
from typing import Optional

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("ToolRegistry")


class ToolRegistry:
    """
    Central registry and router for all ASTA tools.

    Every tool registers itself here. Incoming payloads are routed by the
    "tool_name" or "tool" field to the correct handler.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        "\"""Register a tool instance."""
        if tool.name in self._tools:
            logger.warning(f"[ToolRegistry] Overwriting existing tool: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(f"[ToolRegistry] Registered tool: {tool.name}")

    async def route(self, payload: dict, session_id: str = "") -> dict:
        """
        Route an incoming payload to the correct tool.

        Args:
            payload: Must contain JSON with "tool" field matching a registered tool name.
            session_id: For correlation logging.

        Returns:
            Standard tool result dict. Never raises.
        """
        tool_name = payload.get("tool_name", payload.get("tool", ""))
        action = payload.get("action", payload.get("operation", "unknown"))
        ts = time.strftime("%H:%M:%S")

        if not tool_name:
            logger.error(f"[ToolRegistry:{session_id[:8]}] Missing 'tool_name' or 'tool' field in payload")
            return {
                "status": "error",
                "tool": "unknown",
                "result": {},
                "error": "Missing 'tool_name' or 'tool' field in payload",
                "memory_tag": payload.get("memory_tag", ""),
                "intent": payload.get("intent", ""),
                "execution_time_ms": 0,
            }

        tool = self._tools.get(tool_name)
        if not tool:
            available = list(self._tools.keys())
            logger.error(
                f"[ToolRegistry:{session_id[:8]}] Tool '{tool_name}' not found. "
                f"Available: {available}"
            )
            return {
                "status": "error",
                "tool": tool_name,
                "result": {},
                "error": f"Tool '{tool_name}' not found. Available tools: {available}",
                "memory_tag": payload.get("memory_tag", ""),
                "intent": payload.get("intent", ""),
                "execution_time_ms": 0,
            }

        logger.info(f"[{session_id[:8]}:{tool_name}:{action}:{ts}] Routing to {tool_name}")

        result = await tool.run(payload)

        logger.info(
            f"[{session_id[:8]}:{tool_name}:{action}:{ts}] "
            f"Completed: status={result.get('status')}, "
            f"time={result.get('execution_time_ms')}ms"
        )

        return result

    async def list_tools(self) -> list[dict]:
        "\"""List all registered tools with their descriptions."""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        "\"""Get a tool instance by name."""
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        "\"""List of registered tool names."""
        return list(self._tools.keys())


# -- Global singleton --------------------------------------------------

tool_registry = ToolRegistry()


def register_all_tools():
    """
    Import and register all tool modules.
    Called during server startup.
    """
    try:
        from backend.app.tools.search_tool import SearchTool
        tool_registry.register(SearchTool())
    except Exception as e:
        logger.warning(f"[ToolRegistry] Failed to register SearchTool: {e}")

    try:
        from backend.app.tools.weather_tool import WeatherTool
        tool_registry.register(WeatherTool())
    except Exception as e:
        logger.warning(f"[ToolRegistry] Failed to register WeatherTool: {e}")

    try:
        from backend.app.tools.news_tool import NewsTool
        tool_registry.register(NewsTool())
    except Exception as e:
        logger.warning(f"[ToolRegistry] Failed to register NewsTool: {e}")

    try:
        from backend.app.tools.notion_tool import NotionTool
        tool_registry.register(NotionTool())
    except Exception as e:
        logger.warning(f"[ToolRegistry] Failed to register NotionTool: {e}")

    # Calendar tool disabled - using Notion for task management instead
    # try:
    #     from backend.app.tools.calendar_tool import CalendarTool
    #     tool_registry.register(CalendarTool())
    # except Exception as e:
    #     logger.warning(f"[ToolRegistry] Failed to register CalendarTool: {e}")

    try:
        from backend.app.tools.image_tool import ImageTool
        tool_registry.register(ImageTool())
    except Exception as e:
        logger.warning(f"[ToolRegistry] Failed to register ImageTool: {e}")

    logger.info(f"[ToolRegistry] {len(tool_registry.tool_names)} tools registered: {tool_registry.tool_names}")
