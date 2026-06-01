"""
Turn State Machine for ASTA.

Tracks the lifecycle of a single conversation turn through all states,
ensuring tool results are committed to memory before the turn closes.

States:
  IDLE → LISTENING → PROCESSING → THINKING → TOOL_PENDING → TOOL_EXECUTING
  → TOOL_RESOLVED | TOOL_FAILED → SPEAKING → COMMITTING → IDLE

Thread-safe via asyncio.Lock. Tool results stored for memory commit.
"""

import asyncio
import logging
from enum import Enum
from typing import Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger("TurnState")


class TurnState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    THINKING = "THINKING"
    TOOL_PENDING = "TOOL_PENDING"
    TOOL_EXECUTING = "TOOL_EXECUTING"
    TOOL_RESOLVED = "TOOL_RESOLVED"
    TOOL_FAILED = "TOOL_FAILED"
    SPEAKING = "SPEAKING"
    COMMITTING = "COMMITTING"


# Valid state transitions
VALID_TRANSITIONS = {
    TurnState.IDLE: {TurnState.LISTENING, TurnState.PROCESSING},
    TurnState.LISTENING: {TurnState.PROCESSING, TurnState.IDLE},
    TurnState.PROCESSING: {TurnState.THINKING, TurnState.IDLE},
    TurnState.THINKING: {TurnState.TOOL_PENDING, TurnState.SPEAKING, TurnState.IDLE},
    TurnState.TOOL_PENDING: {TurnState.TOOL_EXECUTING, TurnState.IDLE},
    TurnState.TOOL_EXECUTING: {TurnState.TOOL_RESOLVED, TurnState.TOOL_FAILED, TurnState.IDLE},
    TurnState.TOOL_RESOLVED: {TurnState.SPEAKING, TurnState.COMMITTING, TurnState.IDLE},
    TurnState.TOOL_FAILED: {TurnState.SPEAKING, TurnState.COMMITTING, TurnState.IDLE},
    TurnState.SPEAKING: {TurnState.COMMITTING, TurnState.IDLE},
    TurnState.COMMITTING: {TurnState.IDLE},
}


class InvalidTransition(Exception):
    """Raised when an illegal state transition is attempted."""
    pass


class TurnStateMachine:
    """
    Manages state for a single conversation turn.

    Usage:
        tsm = TurnStateMachine(session_id, turn_id)
        await tsm.transition(TurnState.LISTENING)
        await tsm.transition(TurnState.PROCESSING)
        ...
        # When tool call detected:
        future = await tsm.dispatch_tool(tool_name, parameters)
        result = await tsm.await_tool_completion(timeout=60.0)
        ...
        await tsm.transition(TurnState.COMMITTING)
        await tsm.transition(TurnState.IDLE)
    """

    def __init__(self, session_id: str, turn_id: str):
        self.session_id = session_id
        self.turn_id = turn_id
        self._state = TurnState.IDLE
        self._lock = asyncio.Lock()

        # Tool execution state
        self.tool_future: Optional[asyncio.Future] = None
        self.tool_name: Optional[str] = None
        self.tool_parameters: Optional[dict] = None
        self.tool_result: Optional[Any] = None
        self.tool_error: Optional[str] = None
        self.tool_started_at: Optional[datetime] = None
        self.tool_completed_at: Optional[datetime] = None

    @property
    def state(self) -> TurnState:
        return self._state

    @property
    def has_tool_result(self) -> bool:
        return self.tool_result is not None or self.tool_error is not None

    async def transition(self, new_state: TurnState):
        """
        Transition to a new state. Raises InvalidTransition if illegal.
        """
        async with self._lock:
            valid_targets = VALID_TRANSITIONS.get(self._state, set())
            if new_state not in valid_targets:
                raise InvalidTransition(
                    f"Cannot transition from {self._state.value} to {new_state.value} "
                    f"(valid: {[s.value for s in valid_targets]})"
                )
            old = self._state
            self._state = new_state
            logger.debug(
                f"[TSM:{self.session_id[:8]}:{self.turn_id[:8]}] "
                f"{old.value} -> {new_state.value}"
            )

    async def dispatch_tool(self, tool_name: str, parameters: dict) -> asyncio.Future:
        """
        Set up tool execution. Returns a Future that will hold the result.
        Caller must set the Future result when tool completes.
        """
        async with self._lock:
            self.tool_name = tool_name
            self.tool_parameters = parameters
            self.tool_future = asyncio.get_event_loop().create_future()
            self.tool_started_at = datetime.now(timezone.utc)
            self._state = TurnState.TOOL_PENDING
            logger.info(
                f"[TSM:{self.session_id[:8]}:{self.turn_id[:8]}] "
                f"Tool dispatched: {tool_name}"
            )
            return self.tool_future

    async def resolve_tool(self, result: Any):
        """Mark tool as resolved with result."""
        async with self._lock:
            self.tool_result = result
            self.tool_completed_at = datetime.now(timezone.utc)
            self._state = TurnState.TOOL_RESOLVED
            if self.tool_future and not self.tool_future.done():
                self.tool_future.set_result(result)
            logger.info(
                f"[TSM:{self.session_id[:8]}:{self.turn_id[:8]}] "
                f"Tool resolved: {self.tool_name}"
            )

    async def fail_tool(self, error: str):
        """Mark tool as failed with error."""
        async with self._lock:
            self.tool_error = error
            self.tool_completed_at = datetime.now(timezone.utc)
            self._state = TurnState.TOOL_FAILED
            if self.tool_future and not self.tool_future.done():
                self.tool_future.set_exception(RuntimeError(error))
            logger.warning(
                f"[TSM:{self.session_id[:8]}:{self.turn_id[:8]}] "
                f"Tool failed: {self.tool_name}: {error}"
            )

    async def await_tool_completion(self, timeout: float = 60.0) -> Optional[Any]:
        """
        Block until tool completes or timeout. Returns result or None on timeout.
        """
        if not self.tool_future:
            return None
        try:
            result = await asyncio.wait_for(self.tool_future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self.tool_error = f"Tool {self.tool_name} timed out after {timeout}s"
            self._state = TurnState.TOOL_FAILED
            logger.error(
                f"[TSM:{self.session_id[:8]}:{self.turn_id[:8]}] "
                f"Tool timeout: {self.tool_name} ({timeout}s)"
            )
            return None
        except Exception as e:
            logger.error(
                f"[TSM:{self.session_id[:8]}:{self.turn_id[:8]}] "
                f"Tool error: {e}"
            )
            return None

    def format_tool_result_tag(self) -> str:
        """
        Format the tool result as a structured tag for L1 memory stamp.
        """
        status = "success" if self.tool_result is not None else "failed"
        if self.tool_error and "timed out" in self.tool_error:
            status = "timeout"

        result_text = ""
        if self.tool_result is not None:
            result_text = str(self.tool_result)[:500]
        elif self.tool_error:
            result_text = self.tool_error[:500]

        return (
            f"[TOOL_RESULT: {self.tool_name or 'unknown'}]\n"
            f"Intent: tool execution via OpenClaw\n"
            f"Output: {result_text}\n"
            f"Status: {status}"
        )

    def reset(self):
        """Reset the state machine for a new turn."""
        self._state = TurnState.IDLE
        self.tool_future = None
        self.tool_name = None
        self.tool_parameters = None
        self.tool_result = None
        self.tool_error = None
        self.tool_started_at = None
        self.tool_completed_at = None
