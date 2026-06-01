"""
LLM Router - Intent Classification for Workflow Routing
Uses Groq LLM to classify user intent and route to appropriate workflow.
"""
import logging
from typing import Literal, Dict, Any
from groq import AsyncGroq
from backend.app.config import config

logger = logging.getLogger("LLM_Router")

# Initialize Groq client
client = AsyncGroq(api_key=config.GROQ_API_KEY)


class LLMRouter:
    """
    LLM Router class for workflow LLM calls.
    Provides invoke() and invoke_with_system() methods for workflows.
    """
    
    def __init__(self):
        self.client = client
        
    async def invoke(self, task_type: str, messages: list) -> Dict[str, Any]:
        """
        Invoke LLM with messages.
        
        Args:
            task_type: Type of task (voice_response, quick_response, etc.)
            messages: List of message dicts with role and content
            
        Returns:
            Dict with 'content' key containing the response
        """
        try:
            # Select model based on task type
            model = self._get_model_for_task(task_type)
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            return {"content": content}
            
        except Exception as e:
            logger.error(f"[LLMRouter] invoke failed: {e}")
            return {"content": "I encountered an error processing that request."}
    
    async def invoke_with_system(self, task_type: str, system_prompt: str, user_message: str) -> str:
        """
        Invoke LLM with system prompt and user message.
        
        Args:
            task_type: Type of task
            system_prompt: System prompt
            user_message: User message
            
        Returns:
            String response from LLM
        """
        try:
            model = self._get_model_for_task(task_type)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"[LLMRouter] invoke_with_system failed: {e}")
            return "I encountered an error processing that request."
    
    def _get_model_for_task(self, task_type: str) -> str:
        """Select appropriate model based on task type."""
        # Fast model for classification and quick responses
        if task_type in ["intent_classification", "quick_response"]:
            return "llama-3.1-8b-instant"
        # Larger model for content generation and synthesis
        elif task_type in ["post_generation", "research_synthesis", "script_generation", "content_generation"]:
            return "llama-3.3-70b-versatile"  # Updated to newer model
        # Default to medium model
        else:
            return "llama-3.1-8b-instant"


# Global instance for workflows to import
llm_router = LLMRouter()


INTENT_CLASSIFICATION_PROMPT = """You are ASTA's intent classifier. Analyze the user's message and classify it into ONE of these workflow types:

**research** - Deep research requests requiring web search and synthesis
Examples: "research the latest AI trends", "find information about quantum computing", "what are the best practices for microservices"

**routine** - Daily planning, morning briefings, schedule reviews
Examples: "what's my day looking like", "morning briefing", "what's on my calendar", "plan my day"

**content** - Content creation for social media or blogs
Examples: "write a LinkedIn post about AI", "create a YouTube script on productivity", "draft an Instagram caption"

**chat** - Everything else: casual conversation, quick questions, simple tasks
Examples: "hey what's up", "tell me a joke", "what's the weather", "remind me to call John"

User message: "{user_input}"

Respond with ONLY the workflow type (research/routine/content/chat) and a one-line intent summary.
Format: workflow_type|intent_summary

Example responses:
research|Research latest AI trends and developments
routine|Morning briefing with calendar and priorities
content|Create LinkedIn post about AI developments
chat|Casual greeting and conversation
"""


async def classify_intent(
    user_input: str,
    memory_context: str = "",
    conversation_history: list = None
) -> Dict[str, Any]:
    """
    Classify user intent using LLM.
    
    Args:
        user_input: The user's message
        memory_context: Relevant context from memory layers
        conversation_history: Recent conversation for context
        
    Returns:
        Dict with workflow_type and intent
    """
    try:
        # Build context-aware prompt
        prompt = INTENT_CLASSIFICATION_PROMPT.format(user_input=user_input)
        
        # Add memory context if available
        if memory_context:
            prompt = f"CONTEXT FROM MEMORY:\n{memory_context[:500]}\n\n{prompt}"
        
        # Add conversation history for context
        messages = []
        if conversation_history:
            # Include last 3 messages for context
            messages.extend(conversation_history[-3:])
        
        messages.append({"role": "user", "content": prompt})
        
        # Call Groq with fast model for classification
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast model for classification
            messages=messages,
            temperature=0.3,  # Low temperature for consistent classification
            max_tokens=50
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse response
        if "|" in result:
            workflow_type, intent = result.split("|", 1)
            workflow_type = workflow_type.strip().lower()
            intent = intent.strip()
        else:
            # Fallback parsing
            workflow_type = result.lower()
            intent = user_input[:100]
        
        # Validate workflow type
        valid_workflows = ["research", "routine", "content", "chat"]
        if workflow_type not in valid_workflows:
            logger.warning(f"Invalid workflow type '{workflow_type}', defaulting to 'chat'")
            workflow_type = "chat"
            intent = user_input[:100]
        
        logger.info(f"[LLM Router] Classified as '{workflow_type}': {intent}")
        
        return {
            "workflow_type": workflow_type,
            "intent": intent,
            "confidence": "high"  # Could add confidence scoring later
        }
        
    except Exception as e:
        logger.error(f"[LLM Router] Classification failed: {e}")
        # Fallback to chat workflow on error
        return {
            "workflow_type": "chat",
            "intent": user_input[:100],
            "confidence": "low",
            "error": str(e)
        }


async def classify_content_type(user_input: str) -> Literal["linkedin", "youtube", "instagram", "twitter"]:
    """
    Classify content creation type for content workflow.
    
    Args:
        user_input: The user's content request
        
    Returns:
        Content platform type
    """
    try:
        prompt = f"""Classify this content creation request into ONE platform:
- linkedin (professional posts, articles)
- youtube (video scripts, descriptions)
- instagram (captions, stories)
- twitter (tweets, threads)

User request: "{user_input}"

Respond with ONLY the platform name (linkedin/youtube/instagram/twitter)."""

        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=10
        )
        
        content_type = response.choices[0].message.content.strip().lower()
        
        # Validate
        valid_types = ["linkedin", "youtube", "instagram", "twitter"]
        if content_type not in valid_types:
            logger.warning(f"Invalid content type '{content_type}', defaulting to 'linkedin'")
            content_type = "linkedin"
        
        return content_type
        
    except Exception as e:
        logger.error(f"[LLM Router] Content type classification failed: {e}")
        return "linkedin"  # Default fallback


async def classify_routine_type(user_input: str, timestamp: str) -> Literal["morning", "evening", "on_demand"]:
    """
    Classify routine type based on user input and time.
    
    Args:
        user_input: The user's routine request
        timestamp: ISO timestamp of the request
        
    Returns:
        Routine type
    """
    try:
        from datetime import datetime
        
        # Parse timestamp to get hour
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        hour = dt.hour
        
        # Time-based heuristics
        if 5 <= hour < 12:
            default_type = "morning"
        elif 18 <= hour < 23:
            default_type = "evening"
        else:
            default_type = "on_demand"
        
        # Check user input for explicit mentions
        user_lower = user_input.lower()
        if "morning" in user_lower or "alarm" in user_lower:
            return "morning"
        elif "evening" in user_lower or "night" in user_lower or "review" in user_lower:
            return "evening"
        
        return default_type
        
    except Exception as e:
        logger.error(f"[LLM Router] Routine type classification failed: {e}")
        return "on_demand"


# Quick keyword-based classification (fallback/fast path)
def quick_classify(user_input: str) -> str:
    """
    Fast keyword-based classification without LLM call.
    Used as fallback or for obvious cases.
    """
    user_lower = user_input.lower()
    
    # Research keywords
    research_keywords = ["research", "find information", "look up", "search for", "what are the best"]
    if any(kw in user_lower for kw in research_keywords):
        return "research"
    
    # Routine keywords
    routine_keywords = ["morning", "calendar", "schedule", "what's my day", "plan my day", "briefing"]
    if any(kw in user_lower for kw in routine_keywords):
        return "routine"
    
    # Content keywords
    content_keywords = ["write a post", "create content", "linkedin post", "youtube script", "instagram caption"]
    if any(kw in user_lower for kw in content_keywords):
        return "content"
    
    # Default to chat
    return "chat"
