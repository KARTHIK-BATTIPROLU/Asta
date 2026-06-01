import logging
import asyncio
import os
from groq import AsyncGroq
from backend.app.config import config as settings
from backend.app.models.action_model import ActionRequest
from backend.app.core.registry import registry

logger = logging.getLogger("DeveloperEngine")

class DeveloperEngine:
    """
    ASTA Developer Engine (Groq Default mapping)
    Generates implementation plans, system architecture designs, and coding tasks.
    Saves outputs to the 'ASTA Developer' Notion database. Actual Kali/OpenClaw execution
    (e.g., git commits) is skipped natively until Stage 4 execution.
    """
    def __init__(self):
        self.groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model_name = "llama-3.3-70b-versatile"
        self.dev_db_id = getattr(settings, "NOTION_DEVELOPER_DB", "").strip()

    async def _get_executor(self):
        executor = registry.get("action_executor")
        if not executor:
            logger.warning("[DeveloperEngine] ActionExecutor not found in registry.")
        return executor

    async def plan_implementation(self, project_name: str, context_details: str, session_id: str) -> str:
        """
        Drafts a deep software architecture / implementation plan.
        Saves the markdown directly to Developer DB in Notion.
        """
        executor = await self._get_executor()
        if not executor:
            return "Error: Developer orchestration failed. Executor disconnected."

        logger.info(f"Designing Implementation Plan for '{project_name}' [Session: {session_id}]")

        # Step 1: Draft the architecture map
        draft_plan = await self._draft_plan(project_name, context_details)

        # Step 2: Push to Notion
        notion_status = "Skipped"
        if self.dev_db_id:
            notion_req = ActionRequest(
                session_id=session_id,
                tool_name="notion",
                parameters={
                    "operation": "create_page",
                    "database": "developer",
                    "title": f"[PLAN] {project_name.title()}",
                    "content": draft_plan
                },
                intent=f"Saving architectural plan for {project_name}",
                memory_tag=f"dev:{project_name.lower().replace(' ', '_')}"
            )
            n_res = await executor.execute_action(notion_req)
            notion_status = n_res.status
            if notion_status != "success":
                logger.error(f"[DeveloperEngine] Failed to save plan to Notion: {n_res.result}")
        else:
            logger.warning("[DeveloperEngine] NOTION_DEVELOPER_DB not configured. Skipping Notion sync.")

        # Step 3: Scaffold the actual directory via OpenClaw
        scaffold_req = ActionRequest(
            session_id=session_id,
            tool_name="openclaw_exec",
            parameters={
                "tool": "mkdir",
                "args": ["-p"],
                "target": project_name.lower().replace(" ", "_")
            },
            intent=f"Scaffolding initial workspace directory for {project_name}",
            memory_tag=f"dev:{project_name.lower().replace(' ', '_')}"
        )
        await executor.execute_action(scaffold_req)

        # Step 4: Initialize Git Repository
        git_req = ActionRequest(
            session_id=session_id,
            tool_name="openclaw_exec",
            parameters={
                "tool": "git",
                "args": ["init"],
                "target": project_name.lower().replace(" ", "_")
            },
            intent=f"Initialize git repo for {project_name}",
            memory_tag=f"dev:{project_name.lower().replace(' ', '_')}"
        )
        await executor.execute_action(git_req)

        # Step 5: Audio/Voice confirmation
        return await self._generate_spoken_summary(project_name, notion_status == "success")

    async def _draft_plan(self, project_name: str, context_details: str) -> str:
        """
        Uses Groq Versatile model to architect a coding plan.
        """
        system_prompt = f"""You are ASTA (Developer Mode). Karthik wants to build '{project_name}'.
Review the context details and output a comprehensive software architecture and implementation checklist.
Include:
- System Architecture Map
- Data Models / Schemas
- Step-by-Step Task Checklist
Do NOT write the actual source code. Focus only on the implementation plan.     
"""
        try:
            stream = await self.groq_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context_details[:2000]}
                ],
                temperature=0.3, # Keep dev plans strict
                max_tokens=2500
            )
            return stream.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[DeveloperEngine] Drafting error via Groq: {e}")     
            return f"Failed to draft plan due to an anomaly: {e}"

    async def _generate_spoken_summary(self, project: str, saved_notion: bool) -> str:
        """
        Voice summary using the much faster 8b instant model.
        """
        base = f"I've finished architecting the implementation plan for {project} and scaffolded the repository."
        db_msg = " Checklists successfully synced to your Developer Notion." if saved_notion else ""

        try:
            stream = await self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are ASTA updating Karthik over voice. Combine the status into one spoken conversational sentence."},     
                    {"role": "user", "content": f"Status: {base}{db_msg}"}      
                ],
                temperature=0.4,
                max_tokens=60
            )
            return stream.choices[0].message.content.strip()
        except Exception:
            return base + db_msg

# Singleton instance
developer_engine = DeveloperEngine()
