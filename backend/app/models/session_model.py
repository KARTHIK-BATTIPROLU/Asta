from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class SessionSummary(BaseModel):
    summary: str
    keywords: List[str] = Field(default_factory=list)
    context_tags: List[str] = Field(default_factory=list)

class Session(BaseModel):
    session_id: str
    name: Optional[str] = None
    pinned: bool = False
    archived: bool = False
    priority: float = 0.5
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: str = "active"
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    topic: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    messages: List[Message] = Field(default_factory=list)
    context_tags: List[str] = Field(default_factory=list)
    importance_score: Optional[float] = None
    relevance_score: float = 0.5
    feedback_count: int = 0
    chunk_count: int = 0
    chunk_embeddings: List[List[float]] = Field(default_factory=list)
    
    # Future compatibility for vector embeddings
    embedding: Optional[List[float]] = None 

    class Config:
        arbitrary_types_allowed = True
        extra = "allow" # Allow extra fields for flexibility
