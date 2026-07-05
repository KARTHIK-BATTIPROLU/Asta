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

    async def run_morning_routine(self, user_city: str, session_id: str, lat: float = None, lon: float = None) -> str:
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

        screen_time_warning = ""
        try:
            db = registry.get("db")
            if db and hasattr(db, "neo4j_driver"):
                async with db.neo4j_driver.session() as session:
                    result = await session.run(
                        "MATCH (u:Identity {name: 'KARTHIK'})-[:RECORDED_ON]->(m:DailyMetrics) "
                        "RETURN m.screen_time_minutes AS st, m.sleep_minutes AS sleep "
                        "ORDER BY m.recorded_at DESC LIMIT 1"
                    )
                    record = await result.single()
                    if record:
                        st_mins = record["st"]
                        sleep_mins = record["sleep"]
                        if st_mins and st_mins > 300:
                            screen_time_warning = f"\nCRITICAL CONTEXT: Yesterday's screen time was {st_mins} minutes (over 5 hours). You MUST issue a firm, strict warning about this in the briefing, demanding better discipline today."
                        if sleep_mins and sleep_mins < 360: # less than 6 hours
                            screen_time_warning += f"\nCRITICAL CONTEXT: Karthik only got {round(sleep_mins / 60.0, 1)} hours of sleep last night. Be sympathetic and adjust your tone to be a bit gentler and recommend a lighter day if possible."
                        elif sleep_mins:
                            screen_time_warning += f"\nCONTEXT: Karthik got a solid {round(sleep_mins / 60.0, 1)} hours of sleep. You can mention he's well rested!"
        except Exception as e:
            logger.error(f"[RoutineEngine] Failed to fetch digital wellbeing: {e}")

        # 1. Dispatch parallel data gathering
        tasks = [
            executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="weather",
                parameters={"operation": "should_jog", "city": user_city, "lat": lat, "lon": lon},
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
        habit_streaks = ""
        try:
            db = registry.get("db")
            if db and hasattr(db, "neo4j_driver"):
                async with db.neo4j_driver.session() as session:
                    # Fetch recorded habits
                    streak_res = await session.run(
                        "MATCH (u:Identity {name: 'KARTHIK'})-[:HABIT_STREAK]->(h:Habit) "
                        "RETURN h.name AS name, h.current_streak AS streak "
                        "ORDER BY h.current_streak DESC"
                    )
                    records = await streak_res.data()
                    if records:
                        habit_streaks = "HABIT STREAKS:\n" + "\n".join([f"- {r['name']}: {r['streak']} days" for r in records if r['streak'] > 0])
        except Exception as e:
            logger.error(f"[RoutineEngine] Failed to fetch habit streaks: {e}")

        combined_context = "\n\n".join(context_blocks)
        if habit_streaks:
            combined_context += f"\n\n[{habit_streaks}]"
        
        # 2. Overload Detection
        overload_warning = ""
        if task_count > 8:
            overload_warning = "OVERLOAD DETECTED: Karthik has more than 8 tasks and events scheduled today. Make sure to clearly flag this and suggest dropping or postponing the lowest priority items. Do not force a change or assume they are dropped, just ask if he wants to."

        # 3. Synthesize Spoken Summary with llm_service
        prompt = f"""You are ASTA, synthesizing the morning briefing.
Rules for Morning Briefing:
1. Wake greeting - cheerful, personal. Mention his sleep duration using the provided context.
2. Weather check - mention the weather and give a direct 'should jog' recommendation.
3. News digest - summarize max 2 stories per tech/AI/metaverse topic concisely.
4. Today's schedule - list fixed tasks vs dynamic tasks cleanly.
5. Dynamic Slotting - For any pending tasks that do NOT have a specific time assigned, proactively suggest a specific time slot (e.g. "I suggest you do X at 2 PM") based on calendar gaps.
6. Habit Streaks - Praise Karthik for any ongoing habit streaks and encourage him to keep them up today. If he didn't jog, enforce jogging gently but firmly.
7. Yesterday's pending - mention anything not completed.
8. Remember to sound conversational, natural, and friendly. Do not use bullet points or markdown.
{overload_warning}
{screen_time_warning}

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

    async def run_night_routine(self, session_id: str) -> str:
        """Executes the end-of-day planning session."""
        logger.info(f"Executing Night Routine [Session: {session_id}]")
        executor = await self._get_executor()
        
        pending_tasks = "No pending tasks found."
        try:
            result = await executor.execute_action(ActionRequest(
                session_id=session_id, tool_name="notion",
                parameters={
                    "operation": "query_database", 
                    "database": "routine",
                    "filters": {
                        "property": "Status",
                        "status": {"equals": "Pending"}
                    }
                },
                intent="Night Planning: Checking today's pending tasks",
                memory_tag="routine:night_planning"
            ))
            if result.status == "success":
                pending_tasks = result.result
        except Exception as e:
            logger.error(f"[RoutineEngine] Notion fetch failed for night routine: {e}")

        prompt = f"""You are ASTA, starting the end-of-day planning session for Karthik.
It is 10:30 PM.

Incomplete tasks from today:
{pending_tasks}

Rules for Night Planning:
1. Greet Karthik warmly.
2. Read off the incomplete tasks.
3. Proactively ask Karthik: which tasks he wants to reschedule to tomorrow, which to drop, and what new priorities he has for tomorrow.
4. Keep it conversational, empathetic, and under 80 words.

Generate the plain text spoken response now.
"""
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
            logger.error(f"[RoutineEngine] LLM streaming failed in night routine: {e}")
            return f"Error compiling night routine: {e}"

        return "".join(final_output)

