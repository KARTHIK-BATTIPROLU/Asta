from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class ActionRequest(BaseModel):
    session_id: str
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class ActionResult(BaseModel):
    session_id: str
    tool_name: str
    status: str
    result: str
    latency_ms: float
