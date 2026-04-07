import asyncio
import time
import logging
from typing import Dict, Any

from backend.app.models.action_model import ActionRequest, ActionResult
from backend.app.core.registry import registry
from backend.app.services.l1_cache import l1_manager

logger = logging.getLogger(__name__)

class WebSearchTool:
    """Mock tool simulating a web search API."""
    async def run(self, parameters: Dict[str, Any]) -> str:
        query = parameters.get("query", "")
        # Simulate network delay (modify this parameter to test timeouts > 2.0s)
        delay = parameters.get("delay", 0.5)
        await asyncio.sleep(delay)
        
        # Simulate a large response payload
        long_content = "Here is some search result text. " * 500
        return f"Search Results for '{query}': {long_content}"

class SkillsRetrieverTool:
    """Retrieves user skills and projects via Neo4j Graph."""
    async def run(self, parameters: Dict[str, Any]) -> str:
        user_name = parameters.get("name", "KARTHIK")
        try:
            db_manager = registry.get("db")
            if not db_manager or not hasattr(db_manager, "neo4j_driver"):
                return "Error: Graph DB not configured."
                
            driver = db_manager.neo4j_driver
            query = "MATCH (u:Identity {name: $name})-[:HAS_SKILL]->(s) RETURN s.name AS skill_name"
            
            async with driver.session() as session:
                result = await session.run(query, name=user_name)
                records = await result.data()
                
            skills = [r["skill_name"] for r in records if r.get("skill_name")]
            if skills:
                return f"Skills found for {user_name}: {', '.join(skills)}"
            return f"No skills defined for {user_name}."
        except Exception as e:
            logger.error(f"[SkillsRetrieverTool] Failed: {e}")
            return f"Error retrieving skills: {e}"

class ActionExecutor:
    """
    Dispatches Pydantic-validated tool calls, applies strict timeouts,
    truncates results, audits to MongoDB, and updates the L1.5 cache.
    """
    def __init__(self):
        self.tools = {
            "WebSearch": WebSearchTool(),
            "SkillsRetriever": SkillsRetrieverTool()
        }
        self.timeout_seconds = 2.0
        self.max_result_length = 2000

    async def execute_action(self, request: ActionRequest) -> ActionResult:
        start_time = time.time()
        tool = self.tools.get(request.tool_name)
        
        if not tool:
            return await self._handle_failure(request, "Tool not found", start_time)

        try:
            # 1. Execute with strict timeout
            raw_result = await asyncio.wait_for(
                tool.run(request.parameters), 
                timeout=self.timeout_seconds
            )
            
            # 2. Format and Truncate Result (<500 tokens / ~2000 chars)
            truncated_result = self._truncate_result(str(raw_result))
            status = "success"
            
        except asyncio.TimeoutError:
            truncated_result = f"Error: Tool '{request.tool_name}' timed out after {self.timeout_seconds}s."
            status = "timeout"
            logger.warning(truncated_result)
        except Exception as e:
            truncated_result = f"Error: Tool '{request.tool_name}' failed with {str(e)}"
            status = "error"
            logger.error(truncated_result)

        latency_ms = (time.time() - start_time) * 1000

        # 3. Create Result Model
        result_obj = ActionResult(
            session_id=request.session_id,
            tool_name=request.tool_name,
            status=status,
            result=truncated_result,
            latency_ms=latency_ms
        )

        # 4. Audit to MongoDB
        await self._audit_tool_execution(result_obj)

        # 5. Update Speculative Cache Hook (L1.5 Layer)
        self._update_speculative_cache(result_obj)

        return result_obj

    def _truncate_result(self, text: str) -> str:
        """Limits string to prevent massive prompts breaking token limits."""
        if len(text) > self.max_result_length:
            return text[:self.max_result_length] + "... [TRUNCATED]"
        return text

    async def _audit_tool_execution(self, result: ActionResult):
        """Logs the tool execution outcome to MongoDB collection 'tool_audits'."""
        try:
            db_manager = registry.get("db")
            if db_manager and hasattr(db_manager, "get_collection"):
                collection = db_manager.get_collection("tool_audits")
                if collection is not None:
                    import datetime
                    
                    async def do_insert():
                        doc = {
                            "session_id": result.session_id,
                            "tool_name": result.tool_name,
                            "status": result.status,
                            "latency_ms": result.latency_ms,
                            "result_preview": result.result[:500], # Keep DB footprint small
                            "timestamp": datetime.datetime.now(datetime.timezone.utc)
                        }
                        # If using PyMongo synchronously:
                        if hasattr(collection, "insert_one"):
                            collection.insert_one(doc)

                    # Offload to thread to ensure we don't block event loop if using sync mongodb
                    await asyncio.to_thread(do_insert)
        except Exception as e:
            logger.error(f"[ActionExecutor] Failed to audit tool execution: {e}")

    def _update_speculative_cache(self, result: ActionResult):
        """Injects the tool result into the L1.5 Speculative Cache."""
        try:
            session = l1_manager.get_session(result.session_id)
            if session:
                session.set_speculative_data(f"tool_result_{result.tool_name}", {
                    "tool": result.tool_name,
                    "status": result.status,
                    "data": result.result
                })
                logger.info(f"[ActionExecutor] L1.5 cache updated with result from {result.tool_name}")
        except Exception as e:
            logger.warning(f"[ActionExecutor] Failed to update L1.5 speculative cache: {e}")

    async def _handle_failure(self, request: ActionRequest, message: str, start_time: float) -> ActionResult:
        latency_ms = (time.time() - start_time) * 1000
        result_obj = ActionResult(
            session_id=request.session_id,
            tool_name=request.tool_name,
            status="not_found",
            result=message,
            latency_ms=latency_ms
        )
        await self._audit_tool_execution(result_obj)
        self._update_speculative_cache(result_obj)
        return result_obj

# Global singleton
action_executor = ActionExecutor()
