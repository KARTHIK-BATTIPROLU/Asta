import logging
import asyncio
from typing import Dict, Any, List
from backend.app.config import config as settings
from backend.app.models.action_model import ActionRequest
from backend.app.core.registry import registry
from backend.app.services.llm_service import stream_llm_response

logger = logging.getLogger("RoutineEngine")

class RoutineEngine:
    """
    ASTA Routine Engine
    Manages daily life: Morning Briefing, task tracking, voice reminders,
    promise/deadline capture, and overload detection.
    Strictly uses Groq llama-3.1-8b-instant for all reasoning and synthesis.
    """
    def __init__(self):
        self.model_name = "llama-3.1-8b-instant"

    async def _get_executor(self):
        try:
            return registry.get("action_executor")
        except KeyError:
            logger.warning("[RoutineEngine] ActionExecutor not found in registry.")
            return None

    async def run_morning_routine(self, user_city: str, session_id: str) -> str:
        """
        Executes a comprehensive morning briefing.
        Fetches weather, news, today's calendar, yesterday's pending,
        and fixed/dynamic tasks from the Routine DB.
        """
        executor = await self._get_executor()
        if not executor:
            from backend.app.services.action_executor import ActionExecutor
            executor = ActionExecutor()

        logger.info(f"Executing Morning Briefing [Session: {session_id}]")

        # 1. Dispatch parallel data gathering
        # Wait, the gather should not unpack tasks but await them.
        tasks = [
            executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="weather",
                parameters={"operation": "should_jog", "city": user_city},
                intent="Morning Briefing: Checking weather and jogging conditions",
                memory_tag="routine:morning_briefing"
            )),
            executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="news",
                parameters={"operation": "get_digest", "num_per_topic": 2, "topics": ["technology", "artificial intelligence", "metaverse"]},
                intent="Morning Briefing: Fetching global tech digest",
                memory_tag="routine:morning_briefing"
            )),
            executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="calendar",
                parameters={"operation": "get_today"},
                intent="Morning Briefing: Fetching today's calendar events",
                memory_tag="routine:morning_briefing"
            )),
            executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="calendar",
                parameters={"operation": "get_pending"},
                intent="Morning Briefing: Checking yesterday's pending calendar events",
                memory_tag="routine:morning_briefing"
            )),
            executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="notion",
                parameters={
                    "operation": "query_database", 
                    "database": "routine",
                    "filters": {
                        "property": "Status",
                        "status": {"equals": "Pending"}
                    }
                },
                intent="Morning Briefing: Fetching fixed and dynamic routine tasks that are pending",
                memory_tag="routine:tasks"
            ))
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        context_blocks = []
        task_count = 0

        # Process results
        for step_name, res in zip(["WEATHER", "NEWS", "CALENDAR_TODAY", "CALENDAR_PENDING", "NOTION_TASKS"], results):
            if isinstance(res, Exception) or res.status != "success":
                err = str(res) if isinstance(res, Exception) else res.result
                context_blocks.append(f"[{step_name}]\nError retrieving data: {err}")
            else:
                block_data = res.result
                context_blocks.append(f"[{step_name}]\n{block_data}")
                if step_name in ["CALENDAR_TODAY", "NOTION_TASKS"]:
                    task_count += len([line for line in block_data.split('\n') if len(line.strip()) > 5])

        combined_context = "\n\n".join(context_blocks)
        
        # 2. Overload Detection
        overload_warning = ""
        if task_count > 8:
            overload_warning = "OVERLOAD DETECTED: Karthik has more than 8 tasks and events scheduled today. Make sure to clearly flag this and suggest dropping or postponing the lowest priority items. Do not force a change or assume they are dropped, just ask if he wants to."

        # 3. Synthesize Spoken Summary with llm_service
        prompt = f"""You are ASTA, synthesizing the morning briefing.
Rules for Morning Briefing:
1. Wake greeting - cheerful, personal.
2. Weather check - mention the weather and give a direct 'should jog' recommendation.
3. News digest - summarize max 2 stories per tech/AI/metaverse topic concisely.
4. Today's schedule - list fixed tasks vs dynamic tasks cleanly and clearly.
5. Yesterday's pending - mention anything not completed or pending from Calendar and Notion.
6. Remember to sound conversational, natural, and friendly. Do not use bullet points or markdown.
{overload_warning}

Data Context:
{combined_context}

Generate the plain text spoken briefing now.
"""
        
        logger.info("[RoutineEngine] Requesting synthetic voice response from LLM...")
        final_output = []
        try:
            async for chunk in stream_llm_response(
                user_message=prompt,
                session_id=session_id,
                history=[],
                rag_context=None,
                health_status="full",
                use_deep_reasoning=False
            ):
                final_output.append(chunk)
        except Exception as e:
            logger.error(f"[RoutineEngine] LLM streaming failed: {e}")
            return f"Error compiling morning routine: {e}"

        text_response = "".join(final_output)
        logger.info("[RoutineEngine] Morning routine fully rendered.")
        
        return text_response
