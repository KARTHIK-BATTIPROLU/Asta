"""
LLM Pipeline Hardening Module

Provides production-grade safety, resilience, and security wrapper functions for LLM operations.
Handles timeouts, retries, prompt injection defense, response conditioning, and tool execution safety.
"""

import asyncio
import re
import logging
from typing import Optional, Any, Callable, Dict, List

from backend.app.config import config

logger = logging.getLogger(__name__)

# --- PROMPT INJECTION DEFENSE ---

# Patterns that suggest prompt injection attempts
INJECTION_BLACKLIST = [
    r"ignore\s+previous\s+instructions?",
    r"system\s+prompt",
    r"act\s+as\s+(?!asta)",  # Allow "act as Asta" but block others
    r"override\s+(?:instructions|rules|guidelines)",
    r"forget\s+(?:everything|previous)",
    r"you\s+are\s+no\s+longer",
    r"new\s+instructions?",
    r"disregard\s+(?:previous|all|your)",
]

INJECTION_PATTERN = re.compile("|".join(INJECTION_BLACKLIST), re.IGNORECASE)


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent prompt injection attacks.
    
    Removes or neutralizes common injection patterns while preserving legitimate input.
    
    Args:
        text: Raw user input
        
    Returns:
        Sanitized input text (injection patterns removed or neutralized)
    """
    if not isinstance(text, str) or not text.strip():
        return text
    
    sanitized = text
    
    # Remove injection patterns
    sanitized = INJECTION_PATTERN.sub("", sanitized)
    
    # Clean up multiple spaces
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    
    if sanitized != text:
        logger.debug(f"[SANITIZE] Input sanitized (removed injection patterns)")
    
    return sanitized


# --- RESPONSE CONDITIONING ---

def condition_response(text: str, max_sentences: int = 4) -> str:
    """
    Normalize and trim LLM response to enforce brevity.
    
    Uses regex-based sentence splitting for accurate boundary detection.
    Preserves natural sentence breaks and meaning while enforcing length limits.
    
    Args:
        text: Raw LLM response text
        max_sentences: Maximum sentences to keep (default: 4)
        
    Returns:
        Conditioned response trimmed to sentence limit
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    
    text = text.strip()
    if not text:
        return ""
    
    # Split on sentence boundaries: ., !, ? followed by whitespace
    # Uses lookbehind to preserve punctuation in the sentence
    sentences = re.split(r"(?<=[.!?])\s+", text)
    
    # Filter empty sentences and take first N
    sentences = [s.strip() for s in sentences if s.strip()]
    conditioned = " ".join(sentences[:max_sentences]).strip()
    
    if len(conditioned) < len(text):
        logger.debug(f"[CONDITION] Trimmed response from {len(text)} to {len(conditioned)} chars")
    
    return conditioned


# --- TIMEOUT + RETRY WRAPPER FOR LLM CALLS ---

async def safe_llm_call(
    coro,
    timeout: float = None,
    retries: int = 2,
    fallback: str = "I'm having trouble thinking right now. Please try again.",
) -> str:
    """
    Safely invoke an LLM coroutine with timeout, retry, and fallback.
    
    FEATURES:
    - Centralized timeout enforcement (prevents hanging)
    - Smart retry on transient errors (rate limits, timeouts)
    - Graceful fallback on persistent failures
    - Comprehensive error logging
    
    Args:
        coro: Coroutine for LLM call (e.g., llm.ainvoke(...))
        timeout: Timeout in seconds (default: config.AGENT_TIMEOUT_SECONDS)
        retries: Number of retry attempts (default: 2)
        fallback: Fallback response on failure (default: generic message)
        
    Returns:
        LLM response or fallback message on timeout/error
    """
    timeout = timeout or config.AGENT_TIMEOUT_SECONDS
    
    for attempt in range(retries):
        try:
            logger.debug(f"[LLM_CALL] Attempt {attempt + 1}/{retries} (timeout={timeout}s)")
            
            # Wrap coro in timeout guard
            response = await asyncio.wait_for(coro, timeout=timeout)
            
            logger.debug(f"[LLM_CALL] Success on attempt {attempt + 1}")
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"[LLM_CALL] Timeout on attempt {attempt + 1}/{retries} after {timeout}s")
            if attempt < retries - 1:
                logger.info(f"[LLM_CALL] Retrying...")
                await asyncio.sleep(1)  # Brief backoff before retry
            else:
                logger.error(f"[LLM_CALL] Exhausted retries after timeout")
                return fallback
                
        except Exception as e:
            error_name = type(e).__name__
            
            # Check if error is retryable (transient)
            is_transient = any(
                keyword in str(e).lower() 
                for keyword in ["rate_limit", "429", "temporary", "unavailable"]
            )
            
            logger.warning(f"[LLM_CALL] {error_name} on attempt {attempt + 1}/{retries}: {str(e)[:100]}")
            
            if is_transient and attempt < retries - 1:
                logger.info(f"[LLM_CALL] Retrying transient error...")
                await asyncio.sleep(2)  # Backoff for rate limits
            else:
                if is_transient:
                    logger.error(f"[LLM_CALL] Exhausted retries on transient error")
                else:
                    logger.error(f"[LLM_CALL] Non-retryable error, aborting")
                return fallback
    
    return fallback


# --- SAFE TOOL EXECUTION ---

def safe_tool_call(
    func: Callable,
    args: Dict[str, Any] = None,
    fallback: str = "Tool failed. Continuing without it.",
) -> Any:
    """
    Safely invoke a tool with exception handling.
    
    FEATURES:
    - Catches all exceptions (never crashes pipeline)
    - Logs errors for debugging
    - Returns fallback result to allow pipeline continuation
    
    Args:
        func: Tool callable to invoke
        args: Arguments dict to pass to tool
        fallback: Fallback return value on error (default: error message)
        
    Returns:
        Tool result or fallback value on error
    """
    try:
        args = args or {}
        tool_name = getattr(func, "name", getattr(func, "__name__", "unknown_tool"))
        logger.debug(f"[TOOL_CALL] Executing {tool_name} with args: {list(args.keys())}")

        if hasattr(func, "invoke"):
            result = func.invoke(args)
        else:
            result = func(**args) if isinstance(args, dict) else func(args)

        logger.debug(f"[TOOL_CALL] {tool_name} succeeded")
        return result

    except Exception as e:
        error_name = type(e).__name__
        tool_name = getattr(func, "name", getattr(func, "__name__", "unknown_tool"))
        logger.error(
            f"[TOOL_CALL] {tool_name} failed with {error_name}: {str(e)[:150]}",
            exc_info=False
        )
        return fallback


async def safe_tool_call_async(
    coro,
    timeout: float = None,
    fallback: str = "Tool failed. Continuing without it.",
) -> Any:
    """
    Safely invoke an async tool with timeout and exception handling.
    
    Args:
        coro: Async coroutine to invoke
        timeout: Timeout in seconds (default: config.EXTERNAL_TIMEOUT_SECONDS)
        fallback: Fallback return value on error
        
    Returns:
        Tool result or fallback value on error
    """
    timeout = timeout or config.EXTERNAL_TIMEOUT_SECONDS
    
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        logger.debug(f"[TOOL_CALL_ASYNC] Async tool succeeded")
        return result
        
    except asyncio.TimeoutError:
        logger.error(f"[TOOL_CALL_ASYNC] Async tool timeout after {timeout}s")
        return fallback
        
    except Exception as e:
        error_name = type(e).__name__
        logger.error(
            f"[TOOL_CALL_ASYNC] Async tool failed with {error_name}: {str(e)[:150]}",
            exc_info=False
        )
        return fallback


# --- MEMORY FAILURE HANDLING ---

async def safe_memory_retrieval(
    search_func: Callable,
    query: str,
    top_k: int = 5,
    default_context: str = "",
) -> str:
    """
    Safely retrieve memory context with graceful degradation on failure.
    
    FEATURES:
    - Wraps memory search with error handling
    - Logs failures without crashing pipeline
    - Returns empty context on failure (system continues)
    - Optional timeout for long-running searches
    
    Args:
        search_func: Memory search function to call
        query: Query string for search
        top_k: Number of results to retrieve (default: 2)
        default_context: Default context if search fails (default: empty string)
        
    Returns:
        Formatted context string or default_context on failure
    """
    try:
        from backend.app.core.registry import registry
        db = registry.get("db")
        if db.is_degraded():
            logger.warning("[MEMORY] DB is degraded - skipping memory retrieval")
            return default_context
    except Exception:
        # Keep retrieval path resilient even if health probing fails.
        pass

    try:
        logger.debug(f"[MEMORY] Retrieving similar sessions (top_k={top_k})...")
        
        # Call search function with timeout
        results = await asyncio.wait_for(
            asyncio.to_thread(search_func, query, top_k),
            timeout=8.0  # Memory search should stay bounded
        )
        
        if not results:
            logger.debug(f"[MEMORY] No results found for query")
            return default_context
        
        logger.debug(f"[MEMORY] Found {len(results)} relevant past sessions")
        
        # Prefer hybrid formatter when available for query-aware summaries.
        context = ""
        try:
            from backend.app.services.hybrid_search import format_session_summaries
            context = format_session_summaries(results, query=query)
        except Exception:
            context_lines = []
            for result in results:
                if isinstance(result, dict) and "summary" in result:
                    context_lines.append(f"- {result['summary']}")
            context = "\n".join(context_lines)

        logger.debug(f"[MEMORY] Context assembled ({len(context)} chars)")
        return context
        
    except asyncio.TimeoutError:
        logger.warning(f"[MEMORY] Search timeout (>5s), proceeding without context")
        return default_context
        
    except Exception as e:
        logger.warning(f"[MEMORY] Retrieval failed: {type(e).__name__}: {str(e)[:100]}")
        logger.info("[MEMORY] Continuing without memory context")
        return default_context


# --- ERROR CATEGORIZATION ---

def is_rate_limit_error(error: Exception) -> bool:
    """Check if error is a rate limit (429) or quota error."""
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in ["rate_limit", "429", "quota", "too many"])


def is_timeout_error(error: Exception) -> bool:
    """Check if error is a timeout."""
    return isinstance(error, asyncio.TimeoutError) or "timeout" in str(error).lower()


def is_transient_error(error: Exception) -> bool:
    """Check if error is likely transient and should be retried."""
    # Check type first (asyncio.TimeoutError, etc.)
    if isinstance(error, asyncio.TimeoutError):
        return True
    
    error_str = str(error).lower()
    transient_keywords = [
        "rate_limit", "429", "timeout", "temporary", "unavailable",
        "connection", "network", "refused", "reset"
    ]
    return any(keyword in error_str for keyword in transient_keywords)


# --- RESPONSE VALIDATION ---

def validate_response(response: Any) -> bool:
    """
    Validate that LLM response is well-formed and safe.
    
    Args:
        response: Response object from LLM
        
    Returns:
        True if response is valid, False otherwise
    """
    if response is None:
        return False
    
    # For LangChain responses, check content attribute
    if hasattr(response, "content"):
        content = response.content
        return isinstance(content, str) and len(content.strip()) > 0
    
    # For string responses
    if isinstance(response, str):
        return len(response.strip()) > 0
    
    return False
