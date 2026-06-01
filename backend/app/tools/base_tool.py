"""
BaseTool - Abstract base class for all ASTA tools.

Every tool inherits from BaseTool and implements validate() and execute().
The run() method orchestrates: validate -> execute -> wrap result.

Return format is always:
{
    "status": "success | error | timeout",
    "tool": "<tool_name>",
    "result": {},
    "error": null,
    "memory_tag": "<from payload>",
    "intent": "<from payload>",
    "execution_time_ms": 0
}
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("ToolBase")


class BaseTool(ABC):
    """Abstract base class that all ASTA tools must inherit."""

    name: str = "base"
    description: str = "Base tool - do not use directly."

    @abstractmethod
    async def validate(self, payload: dict) -> tuple[bool, str]:
        """
        Validate the incoming payload before execution.

        Returns:
            (is_valid, error_message) - error_message is empty string if valid.
        """
        ...

    @abstractmethod
    async def execute(self, payload: dict) -> dict:
        """
        Execute the tool operation. Must never raise - always return a result dict.

        Returns:
            {"data": ..., "message": "..."} on success
            {"error": "..."} on failure
        """
        ...

    async def run(self, payload: dict) -> dict:
        """
        Full tool lifecycle: validate -> execute -> wrap result.

        This method NEVER raises. Every outcome is captured in the return dict.
        """
        start = time.monotonic()
        memory_tag = payload.get("memory_tag", "")
        intent = payload.get("intent", "")

        # Phase 1: Validate
        try:
            is_valid, error_msg = await self.validate(payload)
        except Exception as e:
            logger.error(f"[{self.name}] Validation crashed: {type(e).__name__}: {e}")
            return self._wrap("error", {}, f"Validation error: {e}", memory_tag, intent, start)

        if not is_valid:
            logger.warning(f"[{self.name}] Validation failed: {error_msg}")
            return self._wrap("error", {}, error_msg, memory_tag, intent, start)

        # Phase 2: Execute
        try:
            result = await self.execute(payload)
            if not isinstance(result, dict):
                 result = {"data": result}
        except Exception as e:
            logger.error(f"[{self.name}] Execution crashed: {type(e).__name__}: {e}", exc_info=True)
            return self._wrap("error", {}, f"Execution error: {type(e).__name__}: {e}", memory_tag, intent, start)

        # Phase 3: Determine status from result
        status = "success"
        error = None
        if "error" in result and result["error"]:
            status = "error"
            error = result.get("error")
            

        return self._wrap(status, result, error, memory_tag, intent, start)

    def _wrap(
        self,
        status: str,
        result: dict,
        error: Any,
        memory_tag: str,
        intent: str,
        start_time: float,
    ) -> dict:
        """Wrap any tool outcome into the standard ASTA tool result format."""
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        return {
            "status": status,
            "tool": self.name,
            "result": result,
            "error": str(error) if error else None,
            "memory_tag": memory_tag,
            "intent": intent,
            "execution_time_ms": elapsed_ms,
        }
