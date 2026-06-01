import re
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, List


class ToolExecutionState(str, Enum):
    """Turn-level state machine for tool execution lifecycle."""
    IDLE = "idle"
    PENDING = "pending"          # Tool call detected, not yet dispatched
    EXECUTING = "executing"      # Tool dispatched, awaiting result
    RESOLVED = "resolved"        # Tool completed successfully
    FAILED = "failed"            # Tool timed out or errored


# Shell metacharacters that must NEVER appear in tool arguments or targets
SHELL_METACHAR_PATTERN = re.compile(r'[;&|`$(){}\\\<>!\n\r]')
TARGET_SAFE_PATTERN = re.compile(r'^[a-zA-Z0-9._:\-/]+$')


class ActionRequest(BaseModel):
    session_id: str
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    intent: str = Field(default="", description="Why this tool is being run (written to memory)")
    memory_tag: str = Field(default="", description="Project/context label for L2/L3 clustering")

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce args-as-array and reject shell metacharacters at the model boundary."""
        args = v.get("args")
        target = v.get("target", "")

        # If args is provided, it MUST be a list of strings (never a raw command string)
        if args is not None:
            if isinstance(args, str):
                # Auto-convert legacy string args to array for backward compat,
                # but still validate each element
                args = args.split()
                v["args"] = args
            if not isinstance(args, list):
                raise ValueError(f"'args' must be a list of strings, got {type(args).__name__}")

            for i, arg in enumerate(args):
                arg_str = str(arg)
                if SHELL_METACHAR_PATTERN.search(arg_str):
                    raise ValueError(
                        f"Shell metacharacter detected in args[{i}]: '{arg_str}'. "
                        f"Execution blocked for security."
                    )

        # Validate target format
        if target and isinstance(target, str) and target.strip():
            if not TARGET_SAFE_PATTERN.match(target.strip()):
                raise ValueError(
                    f"Invalid target format: '{target}'. "
                    f"Must be alphanumeric with dots, dashes, colons, forward slashes only."
                )

        return v


class ActionResult(BaseModel):
    session_id: str
    tool_name: str
    status: str
    result: str
    latency_ms: float
    intent: str = ""
    memory_tag: str = ""
