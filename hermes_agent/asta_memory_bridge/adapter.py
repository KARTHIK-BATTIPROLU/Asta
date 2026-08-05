"""
Asta Memory Bridge for Hermes Agent
Routes Hermes SessionDB calls to Asta's MemoryEngine.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# Asta imports
from memory.memory_engine import memory_engine

logger = logging.getLogger(__name__)

class AstaSessionDB:
    """
    Duck-types Hermes's SessionDB, routing core read/write operations to Asta's memory engine
    and gracefully no-oping auxiliary features (like CLI session management).
    """
    
    def __init__(self, *args, **kwargs):
        # We maintain an in-memory L0 state because Hermes expects to be able to fetch
        # and modify the current turn's messages synchronously, whereas Asta's
        # persistence happens asynchronously or at the end of the session.
        self._active_sessions: Dict[str, List[Dict[str, Any]]] = {}
    
    def _ensure_session(self, session_id: str):
        if session_id not in self._active_sessions:
            self._active_sessions[session_id] = []

    # --- Core Chat Flow ---
    
    def append_message(self, session_id: str, role: str, content: str, **kwargs) -> int:
        self._ensure_session(session_id)
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self._active_sessions[session_id].append(msg)
        
        # Trigger Asta's mid-session prefetch if it's a user message
        if role == "user" and isinstance(content, str):
            # Fire-and-forget async call
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(memory_engine.on_user_message(session_id, content))
            except RuntimeError:
                # If no running loop, we skip the prefetch (e.g., synchronous tests)
                pass
                
        return len(self._active_sessions[session_id])

    def append_messages_batch(self, session_id: str, messages: List[Dict[str, Any]]) -> tuple[int, int]:
        self._ensure_session(session_id)
        start_idx = len(self._active_sessions[session_id])
        self._active_sessions[session_id].extend(messages)
        return (start_idx, len(messages))
        
    def replace_messages(self, session_id: str, messages: List[Dict[str, Any]], **kwargs) -> None:
        self._active_sessions[session_id] = messages.copy()

    def get_messages(self, session_id: str, **kwargs) -> List[Dict[str, Any]]:
        self._ensure_session(session_id)
        return self._active_sessions[session_id].copy()

    def get_messages_as_conversation(self, session_id: str, **kwargs) -> List[Dict[str, Any]]:
        return self.get_messages(session_id)

    # --- Persistence / Compression ---

    def archive_and_compact(self, session_id: str, compacted_messages: List[Dict[str, Any]], **kwargs) -> None:
        """
        Hermes calls this to save a compacted version of the transcript.
        We route this to Asta's save_session.
        """
        self._ensure_session(session_id)
        messages_to_save = compacted_messages or self._active_sessions[session_id]
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                memory_engine.save_session(
                    session_id=session_id,
                    workflow_type="hermes_chat",
                    messages=messages_to_save,
                    start_time=datetime.utcnow().isoformat()
                )
            )
        except RuntimeError:
            pass
            
        # Keep the compacted messages in our L0 buffer for subsequent turns
        self._active_sessions[session_id] = compacted_messages

    # --- Utility / Context ---
    
    def get_conversation_root(self, session_id: str) -> str:
        return session_id
        
    def search_messages(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Mock FTS5 search. Ideally route to memory_engine.recall, but that's async."""
        return []
        
    def search_sessions(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        return []
        
    def has_archived_messages(self, session_id: str) -> bool:
        return False
        
    def get_meta(self, key: str) -> Optional[str]:
        return None
        
    def set_meta(self, key: str, value: str) -> None:
        pass
        
    def close(self):
        pass

    # --- Catch-all for Hermes auxiliary features (CLI, TUI, telemetry, etc.) ---
    def __getattr__(self, name: str):
        # Return a no-op function that returns sensible defaults (None/False/[]) depending on context
        def _noop(*args, **kwargs):
            logger.debug(f"AstaSessionDB: no-op call to {name}")
            if name.startswith("list_") or name.startswith("get_resume_"):
                return []
            if name.startswith("has_") or name.startswith("session_count_ge"):
                return False
            if name.startswith("session_count") or name.startswith("message_count"):
                return 0
            return None
        return _noop
