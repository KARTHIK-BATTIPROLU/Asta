from typing import TypedDict

class SupervisorState(TypedDict, total=False):
    user_input: str
    intent: str
    task_data: dict
    response: str
    session_id: str
    messages: list
    memory_context: str
    start_time: str
    error: str
    research_context: dict
    content_state: dict
