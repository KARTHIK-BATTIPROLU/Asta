"""
ASTA LangGraph State Schemas
All workflow states for the ASTA system using TypedDict
"""
from typing_extensions import TypedDict
from typing import Annotated, Optional
from langgraph.graph.message import add_messages
import datetime


class ASTABaseState(TypedDict):
    """Base state for all ASTA workflows"""
    session_id: str
    workflow_type: str
    messages: Annotated[list, add_messages]
    current_input: str
    asta_response: str
    memory_context: str          # formatted past context injected from memory engine
    retrieved_memories: list     # raw session dicts from memory layer
    session_summary: str
    needs_clarification: bool
    clarification_question: str
    is_complete: bool
    notion_page_id: Optional[str]
    tools_used: list
    intermediate_stages: list    # [{stage: str, status: str, detail: str, timestamp: str}]
    error: Optional[str]
    start_time: str              # ISO datetime


class RoutineState(ASTABaseState):
    """State for routine/daily task workflows"""
    task_data: dict          # {task, time, priority} for a captured task
    pending_tasks: list
    todays_tasks: list
    weather_data: dict
    news_items: list
    gratitude_entries: list
    rescheduled_tasks: list
    alarm_acknowledged: bool
    nag_count: int
    routine_phase: str  # "morning_alarm"/"morning_brief"/"daytime"/"night_planning"/"general"


class ResearchState(ASTABaseState):
    """State for research workflows"""
    topic: str
    conversation_summary: str
    search_queries: list
    raw_search_results: list
    scraped_content: list
    filtered_sources: list
    research_points: list
    combined_solution: str
    research_complete: bool
    conversation_turn_count: int


class LinkedInState(ASTABaseState):
    """State for LinkedIn content creation workflows"""
    topic: str
    topic_source: str
    discussion_summary: str
    post_body: str
    hashtags: list
    generated_images: list
    selected_image: Optional[str]
    scheduled_time: Optional[str]
    sheet_row_id: Optional[str]
    preferences_applied: dict
    calendar_topics: list


class ContentState(ASTABaseState):
    """State for YouTube and Instagram content workflows"""
    platform: str
    topic: str
    topic_source: str
    research_points: list
    conversation_summary: str
    script_or_caption: str
    metadata: dict
    slides_content: list           # for Instagram carousels


class HabitState(ASTABaseState):
    """State for habit tracking workflows"""
    habit_type: str   # "dsa"/"reading"/"goals"/"gratitude"/"metaverse"/"community"/"general"
    current_habit_data: dict
    action_requested: str
    updated_data: dict
    notion_updates: list


def add_stage(state: dict, stage: str, status: str, detail: str = "") -> list:
    """Helper function to add intermediate stage to state"""
    stages = state.get("intermediate_stages", [])
    stages.append({
        "stage": stage,
        "status": status,
        "detail": detail,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })
    return stages


# Export all states and helper function
__all__ = [
    "ASTABaseState",
    "RoutineState", 
    "ResearchState",
    "LinkedInState",
    "ContentState",
    "HabitState",
    "add_stage"
]