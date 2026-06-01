"""
Supervisor Graph - Master LangGraph Orchestrator
Routes user requests to appropriate workflows (research, routine, content, chat).
"""
import logging
from typing import Dict, Any, Literal
from datetime import datetime

from backend.app.core.states import (
    SupervisorState,
    create_supervisor_state,
    create_research_state,
    create_routine_state,
    create_content_state,
    create_chat_state
)
from backend.app.core.llm_router import classify_intent

logger = logging.getLogger("Supervisor")


# ============================================================================
# SUPERVISOR NODES
# ============================================================================

async def load_memory_node(state: SupervisorState) -> SupervisorState:
    """
    Load memory context for the session.
    Fetches relevant context from memory layers.
    """
    try:
        logger.info(f"[Supervisor] Loading memory for session {state['session_id']}")
        
        # Import memory engine
        from memory import memory_engine
        
        # Get context from memory layers
        context = await memory_engine.get_context_for_session(
            session_id=state["session_id"],
            user_input=state["user_input"],
            workflow_type=state.get("workflow_type", "chat")
        )
        
        # Format context for LLM prompt
        formatted_context = memory_engine.format_context_for_prompt(context)
        
        # Extract entities mentioned
        entities = context.get("entities_spotted", [])
        
        logger.info(f"[Supervisor] Loaded memory context: {len(formatted_context)} chars, {len(entities)} entities")
        
        return {
            **state,
            "memory_context": formatted_context,
            "entities_mentioned": entities
        }
        
    except Exception as e:
        logger.error(f"[Supervisor] Memory loading failed: {e}")
        # Continue without memory context
        return {
            **state,
            "memory_context": "",
            "entities_mentioned": []
        }


async def classify_intent_node(state: SupervisorState) -> SupervisorState:
    """
    Classify user intent and determine workflow type.
    Uses LLM router to analyze user input.
    """
    try:
        logger.info(f"[Supervisor] Classifying intent for: {state['user_input'][:50]}...")
        
        # Classify intent using LLM
        classification = await classify_intent(
            user_input=state["user_input"],
            memory_context=state.get("memory_context", ""),
            conversation_history=state.get("messages", [])
        )
        
        workflow_type = classification["workflow_type"]
        intent = classification["intent"]
        
        logger.info(f"[Supervisor] Classified as '{workflow_type}': {intent}")
        
        return {
            **state,
            "workflow_type": workflow_type,
            "intent": intent
        }
        
    except Exception as e:
        logger.error(f"[Supervisor] Intent classification failed: {e}")
        # Default to chat workflow
        return {
            **state,
            "workflow_type": "chat",
            "intent": state["user_input"][:100],
            "error": f"Classification error: {str(e)}"
        }


async def route_to_workflow(state: SupervisorState) -> Literal["research", "routine", "content", "chat"]:
    """
    Routing function - determines which workflow to execute.
    This is used as a conditional edge in the graph.
    """
    workflow_type = state.get("workflow_type", "chat")
    logger.info(f"[Supervisor] Routing to '{workflow_type}' workflow")
    return workflow_type


async def save_session_node(state: SupervisorState) -> SupervisorState:
    """
    Save session to memory layers.
    Called after workflow completion.
    """
    try:
        logger.info(f"[Supervisor] Saving session {state['session_id']}")
        
        # Import memory engine
        from memory import memory_engine
        
        # Prepare session data
        messages = state.get("messages", [])
        messages.append({"role": "user", "content": state["user_input"]})
        messages.append({"role": "assistant", "content": state.get("asta_response", "")})
        
        # Save to memory
        await memory_engine.save_session(
            session_id=state["session_id"],
            workflow_type=state.get("workflow_type", "chat"),
            messages=messages,
            start_time=state.get("timestamp", datetime.utcnow().isoformat()),
            notion_page_id=state.get("notion_page_id", "")
        )
        
        logger.info(f"[Supervisor] Session saved successfully")
        
        return state
        
    except Exception as e:
        logger.error(f"[Supervisor] Session save failed: {e}")
        # Don't fail the workflow if save fails
        return {
            **state,
            "error": f"Session save error: {str(e)}"
        }


# ============================================================================
# WORKFLOW EXECUTORS
# ============================================================================

async def execute_research_workflow(state: SupervisorState) -> SupervisorState:
    """
    Execute research workflow using the real research_graph.
    Handles deep research with conversation, web search, and Notion saving.
    """
    logger.info(f"[Research] Starting research workflow")
    
    try:
        from backend.app.workflows.research_graph import research_graph
        
        # Create research state from supervisor state (matching state.py schema)
        research_state = {
            "session_id": state["session_id"],
            "workflow_type": "research",
            "messages": state.get("messages", []),
            "current_input": state["user_input"],
            "asta_response": "",
            "memory_context": state.get("memory_context", ""),
            "retrieved_memories": [],
            "session_summary": "",
            "needs_clarification": False,
            "clarification_question": "",
            "is_complete": False,
            "notion_page_id": None,
            "tools_used": [],
            "intermediate_stages": [],
            "error": None,
            "start_time": state.get("timestamp", datetime.utcnow().isoformat()),
            # Research-specific fields
            "topic": "",
            "conversation_summary": "",
            "search_queries": [],
            "raw_search_results": [],
            "scraped_content": [],
            "filtered_sources": [],
            "research_points": [],
            "combined_solution": "",
            "research_complete": False,
            "conversation_turn_count": 0
        }
        
        # Invoke research graph
        result = await research_graph.ainvoke(research_state)
        
        # Extract response and metadata
        response = result.get("asta_response", "Research completed.")
        
        return {
            **state,
            "asta_response": response,
            "notion_page_id": result.get("notion_page_id", ""),
            "tools_used": ["research_graph", "notion_service", "web_search"],
        }
        
    except Exception as e:
        logger.error(f"[Research] Workflow failed: {e}", exc_info=True)
        return {
            **state,
            "asta_response": f"Research workflow encountered an error: {str(e)}",
            "error": str(e)
        }


async def execute_routine_workflow(state: SupervisorState) -> SupervisorState:
    """
    Execute routine workflow using the real routine_graph.
    Handles morning briefs, task management, night planning, and Notion integration.
    """
    logger.info(f"[Routine] Starting routine workflow")
    
    try:
        from backend.app.workflows.routine_graph import routine_graph
        
        # Create routine state from supervisor state (matching state.py schema)
        routine_state = {
            "session_id": state["session_id"],
            "workflow_type": "routine",
            "messages": state.get("messages", []),
            "current_input": state["user_input"],
            "asta_response": "",
            "memory_context": state.get("memory_context", ""),
            "retrieved_memories": [],
            "session_summary": "",
            "needs_clarification": False,
            "clarification_question": "",
            "is_complete": False,
            "notion_page_id": None,
            "tools_used": [],
            "intermediate_stages": [],
            "error": None,
            "start_time": state.get("timestamp", datetime.utcnow().isoformat()),
            # Routine-specific fields
            "pending_tasks": [],
            "todays_tasks": [],
            "weather_data": {},
            "news_items": [],
            "gratitude_entries": [],
            "rescheduled_tasks": [],
            "alarm_acknowledged": False,
            "nag_count": 0,
            "routine_phase": ""
        }
        
        # Invoke routine graph
        result = await routine_graph.ainvoke(routine_state)
        
        # Extract response and metadata
        response = result.get("asta_response", "Routine task completed.")
        
        return {
            **state,
            "asta_response": response,
            "tools_used": ["routine_graph", "notion_service", "weather_service"],
        }
        
    except Exception as e:
        logger.error(f"[Routine] Workflow failed: {e}", exc_info=True)
        return {
            **state,
            "asta_response": f"Routine workflow encountered an error: {str(e)}",
            "error": str(e)
        }


async def execute_content_workflow(state: SupervisorState) -> SupervisorState:
    """
    Execute content creation workflow using the real linkedin_graph.
    Handles LinkedIn post creation with discussion, generation, and Notion logging.
    """
    logger.info(f"[Content] Starting content workflow")
    
    try:
        from backend.app.workflows.linkedin_graph import linkedin_graph
        
        # Create LinkedIn state from supervisor state (matching state.py schema)
        linkedin_state = {
            "session_id": state["session_id"],
            "workflow_type": "content",
            "messages": state.get("messages", []),
            "current_input": state["user_input"],
            "asta_response": "",
            "memory_context": state.get("memory_context", ""),
            "retrieved_memories": [],
            "session_summary": "",
            "needs_clarification": False,
            "clarification_question": "",
            "is_complete": False,
            "notion_page_id": None,
            "tools_used": [],
            "intermediate_stages": [],
            "error": None,
            "start_time": state.get("timestamp", datetime.utcnow().isoformat()),
            # LinkedIn-specific fields
            "topic": "",
            "topic_source": "",
            "discussion_summary": "",
            "post_body": "",
            "hashtags": [],
            "generated_images": [],
            "selected_image": None,
            "scheduled_time": None,
            "sheet_row_id": None,
            "preferences_applied": {},
            "calendar_topics": []
        }
        
        # Invoke LinkedIn graph
        result = await linkedin_graph.ainvoke(linkedin_state)
        
        # Extract response and metadata
        response = result.get("asta_response", "Content created.")
        
        return {
            **state,
            "asta_response": response,
            "tools_used": ["linkedin_graph", "notion_service", "sheets_service"],
        }
        
    except Exception as e:
        logger.error(f"[Content] Workflow failed: {e}", exc_info=True)
        return {
            **state,
            "asta_response": f"Content workflow encountered an error: {str(e)}",
            "error": str(e)
        }


async def execute_chat_workflow(state: SupervisorState) -> SupervisorState:
    """
    Execute simple chat workflow.
    Uses LLM with memory context for conversational responses.
    """
    logger.info(f"[Chat] Starting chat workflow")
    
    try:
        from backend.app.services.llm_service import stream_llm_response
        
        # Build conversation history
        messages = state.get("messages", [])
        
        # Stream LLM response
        response_chunks = []
        async for chunk in stream_llm_response(
            user_message=state["user_input"],
            session_id=state["session_id"],
            history=messages,
            memory_context=state.get("memory_context", "")
        ):
            response_chunks.append(chunk)
        
        full_response = "".join(response_chunks)
        
        logger.info(f"[Chat] Generated response: {len(full_response)} chars")
        
        return {
            **state,
            "asta_response": full_response,
            "tools_used": ["llm_chat"]
        }
        
    except Exception as e:
        logger.error(f"[Chat] Workflow failed: {e}")
        return {
            **state,
            "asta_response": f"Sorry, I encountered an error: {str(e)}",
            "error": str(e)
        }


# ============================================================================
# MAIN SUPERVISOR EXECUTION
# ============================================================================

async def run_supervisor(
    session_id: str,
    user_input: str,
    user_id: str = "karthik",
    workflow_hint: str = None,
    messages: list = None
) -> Dict[str, Any]:
    """
    Main entry point for supervisor graph execution.
    
    Args:
        session_id: Unique session identifier
        user_input: User's message/request
        user_id: User identifier (default: "karthik")
        workflow_hint: Optional hint for workflow routing
        messages: Optional conversation history
        
    Returns:
        Final state dict with asta_response and metadata
    """
    try:
        logger.info(f"[Supervisor] Starting execution for session {session_id}")
        
        # Create initial state
        state = create_supervisor_state(
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            messages=messages or []
        )
        
        # Execute supervisor pipeline
        # 1. Load memory context
        state = await load_memory_node(state)
        
        # 2. Classify intent (unless hint provided)
        if workflow_hint:
            state["workflow_type"] = workflow_hint
            state["intent"] = user_input[:100]
        else:
            state = await classify_intent_node(state)
        
        # 3. Route to appropriate workflow
        workflow_type = state["workflow_type"]
        
        if workflow_type == "research":
            state = await execute_research_workflow(state)
        elif workflow_type == "routine":
            state = await execute_routine_workflow(state)
        elif workflow_type == "content":
            state = await execute_content_workflow(state)
        else:  # chat
            state = await execute_chat_workflow(state)
        
        # 4. Save session to memory
        state = await save_session_node(state)
        
        logger.info(f"[Supervisor] Execution complete: {workflow_type} workflow")
        
        return dict(state)
        
    except Exception as e:
        logger.error(f"[Supervisor] Execution failed: {e}", exc_info=True)
        return {
            "session_id": session_id,
            "user_input": user_input,
            "asta_response": f"I encountered an error processing your request: {str(e)}",
            "error": str(e),
            "workflow_type": "error"
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def quick_chat(user_input: str, session_id: str = None) -> str:
    """
    Quick chat interface - returns just the response string.
    Useful for simple integrations.
    """
    if not session_id:
        from uuid import uuid4
        session_id = f"quick-{uuid4().hex[:8]}"
    
    result = await run_supervisor(
        session_id=session_id,
        user_input=user_input
    )
    
    return result.get("asta_response", "")
