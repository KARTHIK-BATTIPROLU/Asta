import asyncioimport asyncio



















































llm_queue = LLMQueueManager()# Global singleton                await asyncio.sleep(1) # Prevent tight loop on unexpected errors                logger.error(f"[LLM_Queue] Worker encountered error: {e}")            except Exception as e:                break            except asyncio.CancelledError:                    self.queue.task_done()                finally:                    logger.error(f"[LLM_Queue] Task execution failed: {e}")                except Exception as e:                    await task_func(*args, **kwargs)                    logger.debug(f"[LLM_Queue] Executing task: {task_func.__name__}")                try:                task_func, args, kwargs = await self.queue.get()            try:        while True:    async def _worker(self):        await self.queue.put((task_func, args, kwargs))        """        Add a task to the background queue to be executed sequentially.        """    async def enqueue(self, task_func: Callable[..., Any], *args, **kwargs):            logger.info("[LLM_Queue] Background task worker stopped.")            self.worker_task = None                pass            except asyncio.CancelledError:                await self.worker_task            try:            self.worker_task.cancel()        if self.worker_task:    async def stop(self):            logger.info("[LLM_Queue] Background task worker started.")            self.worker_task = asyncio.create_task(self._worker())        if not self.worker_task:    def start(self):        self.worker_task = None        self.queue = asyncio.Queue()    def __init__(self):class LLMQueueManager:logger = logging.getLogger("LLM_Queue")from typing import Callable, Anyimport loggingimport logging
from typing import Callable, Any

logger = logging.getLogger("LLM_Queue")

class LLMQueueManager:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.worker_task = None

    def start(self):
        if not self.worker_task:
            self.worker_task = asyncio.create_task(self._worker())
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
