"""
LangGraph State Definitions for ASTA Workflows
"""
from typing import TypedDict, Literal, Optional, List, Dict, Any
from datetime import datetime


class SupervisorState(TypedDict, total=False):
    """
    Master state for the supervisor graph.
    Routes to research, routine, or content workflows.
    """
    # Session metadata
    session_id: str
    user_id: str
    timestamp: str
    
    # Workflow routing
    workflow_type: Literal["research", "routine", "content", "chat"]
    intent: str  # Classified user intent
    
    # Messages
    user_input: str
    messages: List[Dict[str, str]]  # Full conversation history
    
    # Memory context
    memory_context: str  # Formatted context from memory layers
    entities_mentioned: List[str]  # Entities extracted from user input
    
    # LLM response
    asta_response: str
    
    # Workflow outputs
    notion_page_id: Optional[str]
    telegram_sent: bool
    tools_used: List[str]
    
    # Error handling
    error: Optional[str]
    retry_count: int


class ResearchState(TypedDict, total=False):
    """
    State for research workflow.
    Deep dive into a topic with web search + synthesis.
    """
    # Inherited from supervisor
    session_id: str
    user_id: str
    user_input: str
    memory_context: str
    
    # Research-specific
    research_query: str  # Cleaned/expanded query
    search_results: List[Dict[str, Any]]  # Serper API results
    scraped_content: List[Dict[str, str]]  # Article content
    
    # Synthesis
    synthesis: str  # LLM-generated research summary
    key_findings: List[str]
    sources: List[str]
    
    # Notion output
    notion_page_id: Optional[str]
    notion_url: Optional[str]
    
    # Response
    asta_response: str
    error: Optional[str]


class RoutineState(TypedDict, total=False):
    """
    State for routine workflow.
    Morning alarm, daily planning, evening review.
    """
    # Inherited from supervisor
    session_id: str
    user_id: str
    timestamp: str
    memory_context: str
    
    # Routine type
    routine_type: Literal["morning", "evening", "on_demand"]
    
    # Calendar data
    calendar_events: List[Dict[str, Any]]
    next_meeting: Optional[Dict[str, Any]]
    
    # Weather data
    weather: Dict[str, Any]
    
    # Priorities from memory/Notion
    priorities: List[str]
    ongoing_projects: List[str]
    
    # Generated plan
    daily_plan: str
    focus_areas: List[str]
    
    # Notion output
    notion_page_id: Optional[str]
    
    # Telegram notification
    telegram_message: str
    telegram_sent: bool
    
    # Response
    asta_response: str
    error: Optional[str]


class ContentState(TypedDict, total=False):
    """
    State for content creation workflow.
    LinkedIn posts, YouTube scripts, Instagram captions.
    """
    # Inherited from supervisor
    session_id: str
    user_id: str
    user_input: str
    memory_context: str
    
    # Content type
    content_type: Literal["linkedin", "youtube", "instagram", "twitter"]
    topic: str
    
    # Research phase
    research_results: List[Dict[str, Any]]
    
    # Generation
    draft: str
    formatted_content: str
    hashtags: List[str]
    
    # Platform-specific
    platform_metadata: Dict[str, Any]  # e.g., video length, image specs
    
    # Notion output
    notion_page_id: Optional[str]
    
    # Response
    asta_response: str
    error: Optional[str]


class ChatState(TypedDict, total=False):
    """
    State for simple chat workflow.
    Quick questions, casual conversation, no heavy workflows.
    """
    # Inherited from supervisor
    session_id: str
    user_id: str
    user_input: str
    messages: List[Dict[str, str]]
    memory_context: str
    
    # Tool usage (optional)
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    
    # Response
    asta_response: str
    error: Optional[str]


# Helper functions for state management

def create_supervisor_state(
    session_id: str,
    user_id: str,
    user_input: str,
    memory_context: str = "",
    messages: Optional[List[Dict[str, str]]] = None
) -> SupervisorState:
    """Create initial supervisor state."""
    return SupervisorState(
        session_id=session_id,
        user_id=user_id,
        timestamp=datetime.utcnow().isoformat(),
        user_input=user_input,
        messages=messages or [],
        memory_context=memory_context,
        entities_mentioned=[],
        workflow_type="chat",  # Default, will be classified
        intent="",
        asta_response="",
        notion_page_id=None,
        telegram_sent=False,
        tools_used=[],
        error=None,
        retry_count=0
    )


def create_research_state(supervisor_state: SupervisorState) -> ResearchState:
    """Create research state from supervisor state."""
    return ResearchState(
        session_id=supervisor_state["session_id"],
        user_id=supervisor_state["user_id"],
        user_input=supervisor_state["user_input"],
        memory_context=supervisor_state.get("memory_context", ""),
        research_query="",
        search_results=[],
        scraped_content=[],
        synthesis="",
        key_findings=[],
        sources=[],
        notion_page_id=None,
        notion_url=None,
        asta_response="",
        error=None
    )


def create_routine_state(supervisor_state: SupervisorState) -> RoutineState:
    """Create routine state from supervisor state."""
    return RoutineState(
        session_id=supervisor_state["session_id"],
        user_id=supervisor_state["user_id"],
        timestamp=supervisor_state.get("timestamp", datetime.utcnow().isoformat()),
        memory_context=supervisor_state.get("memory_context", ""),
        routine_type="on_demand",
        calendar_events=[],
        next_meeting=None,
        weather={},
        priorities=[],
        ongoing_projects=[],
        daily_plan="",
        focus_areas=[],
        notion_page_id=None,
        telegram_message="",
        telegram_sent=False,
        asta_response="",
        error=None
    )


def create_content_state(supervisor_state: SupervisorState) -> ContentState:
    """Create content state from supervisor state."""
    return ContentState(
        session_id=supervisor_state["session_id"],
        user_id=supervisor_state["user_id"],
        user_input=supervisor_state["user_input"],
        memory_context=supervisor_state.get("memory_context", ""),
        content_type="linkedin",  # Default, will be classified
        topic="",
        research_results=[],
        draft="",
        formatted_content="",
        hashtags=[],
        platform_metadata={},
        notion_page_id=None,
        asta_response="",
        error=None
    )


def create_chat_state(supervisor_state: SupervisorState) -> ChatState:
    """Create chat state from supervisor state."""
    return ChatState(
        session_id=supervisor_state["session_id"],
        user_id=supervisor_state["user_id"],
        user_input=supervisor_state["user_input"],
        messages=supervisor_state.get("messages", []),
        memory_context=supervisor_state.get("memory_context", ""),
        tool_calls=[],
        tool_results=[],
        asta_response="",
        error=None
    )
