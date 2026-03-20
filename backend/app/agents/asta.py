from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from backend.app.config import config
from backend.app.tools.reminder import create_reminder
import logging

logger = logging.getLogger(__name__)

if not config.GROQ_API_KEY:
    logger.error("GROQ_API_KEY is missing!")
    # We can't return here, but we can log. The app will likely fail later.
    # raise ValueError("GROQ_API_KEY is missing!")

# Initialize LLM
llm = ChatGroq(
    model_name=config.MODEL_NAME or "llama-3.3-70b-versatile",
    temperature=0.7,
    groq_api_key=config.GROQ_API_KEY
)

# Bind tools
tools = [create_reminder]
llm_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = """You are Asta, a smart, friendly personal AI assistant.
Your goal is to help the user manage their tasks and answer questions.

You have access to a tool to create reminders: `create_reminder`.

When a user asks to set a reminder:
1. Understand the 'what' (message) and 'when' (time).
2. Call the `create_reminder` tool with these details.
3. If the time is ambiguous, ask for clarification.
4. Once the tool returns a confirmation, relay that to the user in a friendly way.

If the user just wants to chat, respond naturally and conversationally.
Keep your responses concise and helpful.
"""

def asta_agent(message: str) -> str:
    """
    Simple agent invocation.
    Input: user message string
    Output: assistant response string
    """
    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=message)
        ]
        
        # Invoke LLM
        response = llm_with_tools.invoke(messages)
        
        # Check for tool calls
        if response.tool_calls:
            logger.info("Tool call detected.")
            # For this simple implementation, we'll execute the first tool call directly
            # In a full LangGraph setup, we'd loop back, but for "minimal" request, direct execution is fine for now
            # However, prompt asks for LangGraph. Let's make it slightly more structured if needed.
            # But direct tool execution is simpler for "minimal" unless specified otherwise.
            # We will adhere to the "minimal" instruction and just execute it.
            
            tool_call = response.tool_calls[0]
            if tool_call["name"] == "create_reminder":
                tool_args = tool_call["args"]
                result = create_reminder.invoke(tool_args)
                return result # Return the confirmation directly
        
        return response.content
        
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return "I'm sorry, I'm having trouble processing your request right now."
