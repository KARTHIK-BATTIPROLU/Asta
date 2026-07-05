"""
Task Registry for ASTA.

Provides centralized tracking, supervision, and failure logging for all background
asyncio tasks. Every task in the system MUST be registered through TaskRegistry.track()
instead of bare asyncio.create_task().

Failures are:
  1. Logged with full traceback
  2. Persisted to MongoDB `task_failures` collection for queryability
  3. Never silently swallowed
"""

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Set

from backend.app.db.database import db_manager

logger = logging.getLogger("TaskRegistry")


class TaskRegistry:
    """
    Singleton registry for all background asyncio tasks.
    
    Usage:
        TaskRegistry.track(
            asyncio.create_task(some_coroutine()),
            name="memory_overflow_pipeline",
            session_id="abc123"
        )
    """
    _instance = None
    _tasks: Dict[str, Set[asyncio.Task]] = {}      # session_id -> set of tasks
    _global_tasks: Set[asyncio.Task] = set()         # tasks without session_id

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tasks = {}
            cls._global_tasks = set()
        return cls._instance

    @classmethod
    def track(
        cls,
        coro_or_task,
        name: str,
        session_id: Optional[str] = None,
    ) -> asyncio.Task:
        """
        Register and supervise a background task.
        
        Args:
            coro_or_task: A coroutine or an already-created Task
            name: Human-readable name for logging and failure records
            session_id: Optional session scope for cancel_all()
            
        Returns:
            The tracked asyncio.Task
        """
        # Accept either a coroutine or a pre-created task
        if asyncio.iscoroutine(coro_or_task):
            task = asyncio.create_task(coro_or_task, name=name)
        elif isinstance(coro_or_task, asyncio.Task):
            task = coro_or_task
            task.set_name(name)
        else:
            raise TypeError(f"Expected coroutine or Task, got {type(coro_or_task).__name__}")

        # Register in the appropriate tracking set
        if session_id:
            if session_id not in cls._tasks:
                cls._tasks[session_id] = set()
            cls._tasks[session_id].add(task)
        else:
            cls._global_tasks.add(task)

        # Attach done callback for supervision
        task.add_done_callback(
            lambda t: cls._on_task_done(t, name, session_id)
        )

        logger.debug(f"[TaskRegistry] Tracking task '{name}' (session={session_id or 'global'})")
        return task

    @classmethod
    def _on_task_done(
        cls,
        task: asyncio.Task,
        name: str,
        session_id: Optional[str],
    ):
        """Done callback: log result, persist failures to MongoDB."""
        # Remove from tracking set
        if session_id and session_id in cls._tasks:
            cls._tasks[session_id].discard(task)
            if not cls._tasks[session_id]:
                del cls._tasks[session_id]
        else:
            cls._global_tasks.discard(task)

        # Handle cancellation
        if task.cancelled():
            logger.info(f"[TaskRegistry] Task '{name}' cancelled (session={session_id or 'global'})")
            return

        # Handle exception
        exc = task.exception()
        if exc:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            logger.error(
                f"[TaskRegistry] Task '{name}' FAILED (session={session_id or 'global'}): "
                f"{type(exc).__name__}: {exc}\n{tb_str}"
            )
            # Persist failure to MongoDB (fire-and-forget since this is a callback)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    cls._persist_failure(name, session_id, exc, tb_str)
                )
            except RuntimeError:
                # No running loop (shutdown) — just log
                logger.warning(f"[TaskRegistry] Cannot persist failure for '{name}' — no event loop")
        else:
            logger.debug(f"[TaskRegistry] Task '{name}' completed successfully")

    @classmethod
    async def _persist_failure(
        cls,
        task_name: str,
        session_id: Optional[str],
        exc: BaseException,
        tb_str: str,
    ):
        """Write task failure to MongoDB `task_failures` collection."""
        try:
            if db_manager.db is None:
                logger.warning("[TaskRegistry] Cannot persist failure — DB not connected")
                return

            collection = db_manager.db["task_failures"]
            doc = {
                "task_name": task_name,
                "session_id": session_id or "global",
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                "traceback": tb_str[:2000],
                "timestamp": datetime.now(timezone.utc),
                "retry_count": 0,
            }
            await collection.insert_one(doc)
            logger.info(f"[TaskRegistry] Failure persisted for task '{task_name}'")
        except Exception as persist_err:
            logger.error(f"[TaskRegistry] Failed to persist task failure: {persist_err}")

    @classmethod
    def cancel_all(cls, session_id: str) -> int:
        """Cancel all tasks for a given session. Returns count of cancelled tasks."""
        tasks = cls._tasks.pop(session_id, set())
        cancelled = 0
        for task in tasks:
            if not task.done():
                task.cancel()
                cancelled += 1
        if cancelled:
            logger.info(f"[TaskRegistry] Cancelled {cancelled} tasks for session {session_id[:8]}")
        return cancelled

    @classmethod
    def get_active(cls, session_id: Optional[str] = None) -> list:
        """Return all running tasks for a session (or global if None)."""
        if session_id:
            tasks = cls._tasks.get(session_id, set())
        else:
            tasks = cls._global_tasks
        return [
            {
                "name": t.get_name(),
                "done": t.done(),
                "cancelled": t.cancelled(),
            }
            for t in tasks
        ]

    @classmethod
    def get_all_active_count(cls) -> int:
        """Total number of tracked running tasks across all sessions."""
        count = sum(
            1 for t in cls._global_tasks if not t.done()
        )
        for tasks in cls._tasks.values():
            count += sum(1 for t in tasks if not t.done())
        return count

    @classmethod
    async def shutdown(cls, cancel_timeout: float = 3.0):
        """
        Cancel all registered background tasks and await their completion or timeout.
        """
        logger.info("[TaskRegistry] Starting shutdown, cancelling all active tasks...")
        
        # Collect all active tasks
        all_tasks = list(cls._global_tasks)
        for session_tasks in cls._tasks.values():
            all_tasks.extend(session_tasks)
            
        active_tasks = [t for t in all_tasks if not t.done()]
        if not active_tasks:
            logger.info("[TaskRegistry] No active tasks to cancel")
            return
            
        logger.info(f"[TaskRegistry] Cancelling {len(active_tasks)} active tasks...")
        for task in active_tasks:
            task.cancel()
            
        # Await completion
        try:
            await asyncio.wait_for(
                asyncio.gather(*active_tasks, return_exceptions=True),
                timeout=cancel_timeout
            )
            logger.info("[TaskRegistry] All tasks successfully completed/cancelled")
        except asyncio.TimeoutError:
            stragglers = [t.get_name() for t in active_tasks if not t.done()]
            logger.warning(f"[TaskRegistry] Shutdown timed out. {len(stragglers)} tasks still running: {stragglers}")


# Singleton instance
task_registry = TaskRegistry()
