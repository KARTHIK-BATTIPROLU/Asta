import re
import logging
from enum import Enum
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("ActionDispatcher")

class IntentType(str, Enum):
    IDENTITY = "identity"   # Personal user data (skills, projects)
    KNOWLEDGE = "knowledge" # Requires external search or heavy RAG
    ACTION = "action"       # Requires API tools, alarms, smart-home
    CHITCHAT = "chitchat"   # Fast conversational response

# Tool Schemas for Phase C
class WebSearch(BaseModel):
    query: str
    rationale: str

class TaskReminder(BaseModel):
    action: str
    target_time: str
    context: Optional[str] = None

class MemoryUpdate(BaseModel):
    key: str
    value: str

class ActionDispatcher:
    """
    ASTA Phase C - Agentic Layer Heuristic Router.
    Uses regex rules to rapidly classify partial or full transcripts into intents
    to trigger Speculative Tool Execution or Standard RAG.
    """
    def __init__(self):
        self.identity_patterns = [
            r"\bskill(s)?\b", r"\bexperience\b", r"\bwhat do i know\b", r"\bmy projects\b"
        ]
        self.action_patterns = [
            r"\bremind me\b", r"\bschedule\b", r"\bset (an|a)? alarm\b",
            r"\bturn (on|off)\b", r"\bcreate a task\b"
        ]
        self.knowledge_patterns = [
            r"\bsearch for\b", r"\blook up\b", r"\bwho is\b", r"\bwhat is\b",
            r"\bhow to\b", r"\bwhy did\b", r"\btell me about\b"
        ]
        
        self.identity_regex = re.compile("|".join(self.identity_patterns), re.IGNORECASE)
        self.action_regex = re.compile("|".join(self.action_patterns), re.IGNORECASE)
        self.knowledge_regex = re.compile("|".join(self.knowledge_patterns), re.IGNORECASE)

    def route_intent(self, transcript: str) -> IntentType:
        """Heuristically route transcript to 1 of 4 intent categories (< 2ms)"""
        # Heuristic order of precedence
        if self.identity_regex.search(transcript):
            return IntentType.IDENTITY
        if self.action_regex.search(transcript):
            return IntentType.ACTION
        if self.knowledge_regex.search(transcript):
            return IntentType.KNOWLEDGE
        return IntentType.CHITCHAT

dispatcher = ActionDispatcher()
