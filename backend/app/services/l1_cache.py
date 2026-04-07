import collections
import tiktoken
import asyncio
import logging
from backend.app.services.memory_orchestrator import orchestrator

logger = logging.getLogger("L1_Buffer")

class SessionL1Cache:
    def __init__(self, session_id: str, max_tokens: int = 2000):
        self.session_id = session_id
        self.max_tokens = max_tokens
        self.buffer = collections.deque()
        self.current_tokens = 0
        self._lock = asyncio.Lock()
        self._active_tasks = set()
        
        # L1.5 Speculative Layer
        self.speculative_context = {}
        self._speculative_lock = asyncio.Lock()

        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.encoder = tiktoken.get_encoding("gpt2")

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoder.encode(text))

    async def set_speculative_data(self, key: str, data: str, ttl: int = 10, trigger_query: str = ""):
        expires_at = asyncio.get_event_loop().time() + ttl
        async with self._speculative_lock:
            self.speculative_context[key] = {
                "data": data,
                "expires_at": expires_at,
                "trigger_query": trigger_query
            }
        logger.info(f"[L1.5 Cache] Set speculative context for '{key}' (TTL: {ttl}s)")

    async def get_speculative_data(self, key: str) -> dict | None:
        async with self._speculative_lock:
            if key in self.speculative_context:
                record = self.speculative_context[key]
                if asyncio.get_event_loop().time() < record["expires_at"]:
                    logger.info(f"[L1.5 Cache] HIT for '{key}' (0ms delay)")
                    return record
                else:
                    logger.info(f"[L1.5 Cache] EXPIRED for '{key}'")
                    del self.speculative_context[key]
        return None

    async def append_turn(self, user_text: str, assistant_text: str):
        # Calculate strict Tiktoken mapped bytes length
        user_toks = await asyncio.to_thread(self.count_tokens, user_text)
        assistant_toks = await asyncio.to_thread(self.count_tokens, assistant_text)
        turn_toks = user_toks + assistant_toks

        async with self._lock:
            # In-Memory Register FIRST
            new_turn = {
                "user": user_text,
                "assistant": assistant_text,
                "tokens": turn_toks
            }
            self.buffer.append(new_turn)
            self.current_tokens += turn_toks

            # Sliding Window Math: Evict oldest until we are under max_tokens
            while self.buffer and self.current_tokens > self.max_tokens:
                popped_turn = self.buffer.popleft()
                self.current_tokens -= popped_turn["tokens"]
                await self._trigger_l2_eviction(popped_turn)

        logger.info(f"[L1] Turn registered ({turn_toks} tx). L1 Pool: {self.current_tokens}/{self.max_tokens}")

    async def _trigger_l2_eviction(self, turn: dict):
        user_text = turn["user"]
        assistant_text = turn["assistant"]
        logger.info(f"[L1->L2] Evicting boundary turn ({turn['tokens']} tx) securely to MongoDB.")

        async def _async_evict():
            try:
                content_payload = f"User: {user_text}\nASTA: {assistant_text}"
                # 1. Pipeline hook: Triggers Extractive/Abstractive RAG seamlessly executing Autonomous Graph Extractions natively asynchronously.
                await orchestrator.process_overflow(self.session_id, content_payload)
            except Exception as e:
                logger.error(f"[L2 Evict] Background sync failure: {e}", exc_info=True)

        # Non-blocking event loop offload
        task = asyncio.create_task(_async_evict())
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def get_llm_history(self) -> list[dict]:
        """Returns the O(1) natively formatted LLM conversation arrays."""
        messages = []
        for turn in self.buffer:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})
        return messages


class L1BufferManager:
    def __init__(self):
        # Global Uvicorn Dictionary Mapping {session_id -> SessionL1Cache}
        self.sessions = {}

    def get_session(self, session_id: str, max_tokens: int = 2000) -> SessionL1Cache:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionL1Cache(session_id, max_tokens)
        return self.sessions[session_id]

    async def clear_session(self, session_id: str):
        if session_id in self.sessions:
            # Force flush EVERYTHING as a single batch to L2 prior to deletion
            session_cache = self.sessions[session_id]
            if session_cache.buffer:
                logger.info(f"[L1->L2] Batch evicting {len(session_cache.buffer)} remaining turns.")
                
                # Combine all remaining turns into one big payload
                combined_payload = ""
                for turn in session_cache.buffer:
                    combined_payload += f"User: {turn['user']}\nASTA: {turn['assistant']}\n"
                
                try:
                    import backend.app.services.memory_orchestrator as mo
                    await mo.orchestrator.process_overflow(session_id, combined_payload.strip())
                except Exception as e:
                    logger.error(f"[L1 Eviction] Failed to batch flush session on close: {e}", exc_info=True)
                    
            del self.sessions[session_id]

l1_manager = L1BufferManager()
