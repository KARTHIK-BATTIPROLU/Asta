import asyncio
import logging
from typing import Callable, Any
from backend.app.core.task_registry import TaskRegistry

logger = logging.getLogger("LLM_Queue")

class LLMQueueManager:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.worker_task = None

    def start(self):
        if not self.worker_task:
            self.worker_task = TaskRegistry.track(
                self._worker(),
                name="llm_queue_worker",
            )
            logger.info("[LLM_Queue] Background task worker started.")

    async def stop(self):
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            logger.info("[LLM_Queue] Background task worker stopped.")

    async def enqueue(self, task_func: Callable[..., Any], *args, **kwargs):
        """
        Add a task to the background queue to be executed sequentially.
        """
        self.start()
        await self.queue.put((task_func, args, kwargs))

    async def _worker(self):
        while True:
            try:
                task_func, args, kwargs = await self.queue.get()
                try:
                    logger.debug(f"[LLM_Queue] Executing task: {task_func.__name__}")
                    await task_func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"[LLM_Queue] Task execution failed: {e}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[LLM_Queue] Worker encountered error: {e}")
                await asyncio.sleep(1) # Prevent tight loop on unexpected errors

# Global singleton
llm_queue = LLMQueueManager()
