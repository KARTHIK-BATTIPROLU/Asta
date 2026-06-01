"""
L1 Session Manager for ASTA
In-memory sliding window with 2000 token limit
"""
import logging
from collections import deque
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("L1Session")


@dataclass
class L1Session:
    """
    In-memory session with sliding window.
    Tracks messages and enforces 2000 token limit.
    """
    session_id: str
    user_id: str
    messages: deque = field(default_factory=deque)
    token_count: int = 0
    max_tokens: int = 2000
    
    def add_message(self, role: str, content: str, tokens: int):
        """
        Add message to session.
        If token limit exceeded, triggers overflow.
        """
        self.messages.append({
            "role": role,
            "content": content,
            "tokens": tokens
        })
        self.token_count += tokens
        
        # Check if overflow needed
        if self.token_count > self.max_tokens:
            logger.info(f"Session {self.session_id} exceeded {self.max_tokens} tokens - overflow triggered")
            return True  # Signal overflow
        
        return False
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages in session"""
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.messages
        ]
    
    def clear(self):
        """Clear session messages"""
        self.messages.clear()
        self.token_count = 0


class L1SessionManager:
    """
    Manages all active L1 sessions.
    Creates new sessions and tracks token counts.
    """
    
    def __init__(self):
        self.sessions: Dict[str, L1Session] = {}
        logger.info("L1SessionManager initialized")
    
    def create_session(self, session_id: str, user_id: str = "karthik") -> L1Session:
        """Create new L1 session"""
        session = L1Session(
            session_id=session_id,
            user_id=user_id
        )
        self.sessions[session_id] = session
        logger.info(f"Created L1 session: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[L1Session]:
        """Get existing session"""
        return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str):
        """Remove session from memory"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Removed L1 session: {session_id}")
    
    def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation: ~4 chars per token.
        This is approximate - real tokenization would be more accurate.
        """
        return len(text) // 4


# Global instance
l1_manager = L1SessionManager()
