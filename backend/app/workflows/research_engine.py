import logging
import asyncio
import json
from typing import Dict, Any, List
from groq import AsyncGroq
from backend.app.config import config as settings
from backend.app.models.action_model import ActionRequest
from backend.app.core.registry import registry

logger = logging.getLogger("ResearchEngine")


class ResearchEngine:
    """
    ASTA Research Engine (Llama-3.3-70b-versatile)
    Orchestrates deep agentic and quick research workflows. Chains web search results into
    structured Notion pages within the ASTA Research Database, organizing 1 page per project.
    """

    def __init__(self):
        self.groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.reasoning_model = "llama-3.3-70b-versatile"
        self.voice_model = "llama-3.1-8b-instant"
        self.research_db_id = getattr(settings, "NOTION_RESEARCH_DB", "").strip()

    async def _get_executor(self):
        executor = registry.get("action_executor")
        if not executor:
            logger.warning("[ResearchEngine] ActionExecutor not found in registry.")
        return executor

    async def conduct_research(
        self, topic: str, session_id: str, depth: str = "quick", project_name: str = "General"
    ) -> str:
        """
        Conducts research on a topic, synthesizes it, and saves to Notion inside project_name page.
        depth: 'quick' or 'deep_agentic'
        """
        executor = await self._get_executor()
        if not executor:
            return "Error: Research subsystems offline."

        logger.info(f"Starting Research: '{topic}' (Depth: {depth} | Project: {project_name}) [Session: {session_id}]")

        # --- STEP 1: Search ---
        if depth == "deep_agentic":
            raw_search_data = await self._do_deep_agentic_search(executor, session_id, topic)
        else:
            raw_search_data = await self._do_quick_search(executor, session_id, topic)

        if "Search failed" in raw_search_data and not raw_search_data.strip().startswith("QUICK") and not "--- RESULTS FOR QUERY:" in raw_search_data:
            return f"I couldn't fetch research data for {topic} due to a network error."

        # --- STEP 2: Synthesize Report ---
        logger.info(f"[ResearchEngine] Synthesizing report for {topic}...")
        synthesized_content = await self._synthesize_research(topic, project_name, raw_search_data, depth)

        # --- STEP 3: Save to Notion (1 Page / Project) ---
        notion_status = "Skipped"
        if self.research_db_id:
            notion_status = await self._save_to_notion(executor, session_id, project_name, topic, synthesized_content)
        else:
            logger.warning("[ResearchEngine] NOTION_RESEARCH_DB not set. Skipping Notion save.")

        # --- STEP 4: Spoken summary ---
        return await self._generate_spoken_summary(topic, synthesized_content, notion_status == "success")

    async def _do_quick_search(self, executor, session_id: str, topic: str) -> str:
        req = ActionRequest(
            session_id=session_id,
            tool_name="search",
            parameters={"operation": "deep_search", "query": topic[:200], "num_results": 3},
            intent=f"Quick searching topic: {topic}",
            memory_tag=f"research_quick:{topic.lower().replace(' ', '_')}"
        )
        res = await executor.execute_action(req)
        if res.status != "success":
            return f"Search failed: {res.result}"
        return f"QUICK SEARCH RESULTS for '{topic}':\n{res.result}"

    async def _do_deep_agentic_search(self, executor, session_id: str, topic: str) -> str:
        # LLM breaks topic into 3 specific queries
        queries = await self._generate_subqueries(topic)
        logger.info(f"[ResearchEngine] Deep Agentic Queries: {queries}")

        tasks = []
        for q in queries:
            req = ActionRequest(
                session_id=session_id,
                tool_name="search",
                parameters={"operation": "deep_search", "query": q[:200], "num_results": 2},
                intent=f"Deep search querying: {q}",
                memory_tag=f"research_deep:{q.lower().replace(' ', '_')}"
            )
            tasks.append(executor.execute_action(req))
            
        results = await asyncio.gather(*tasks)
        
        aggregated_data = ""
        for idx, res in enumerate(results):
            if res.status == "success":
                aggregated_data += f"\n--- RESULTS FOR QUERY: '{queries[idx]}' ---\n{res.result}\n"
        
        if not aggregated_data.strip():
            return "Search failed: Could not retrieve data for any subquery."
            
        return aggregated_data

    async def _generate_subqueries(self, topic: str) -> List[str]:
        system_prompt = f"""You are a research planner. The user wants to deeply understand: "{topic}".
Provide exactly 3 distinct, highly targeted web search queries that would yield the most comprehensive and diverse facts, technical details, or latest news on this topic.
Format your response as a strict JSON array of strings, with NO markdown formatting, NO backticks, and NO other text."""
        try:
            stream = await self.groq_client.chat.completions.create(
                model=self.reasoning_model,
                messages=[{"role": "system", "content": system_prompt}],
                temperature=0.2,
                max_tokens=500
            )
            response_text = stream.choices[0].message.content.strip()
            # clean backticks if LLM accidentally outputs them
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            queries = json.loads(response_text.strip())
            if isinstance(queries, list) and len(queries) > 0:
                return [str(q) for q in queries[:4]]
        except Exception as e:
            logger.error(f"[ResearchEngine] Error generating subqueries: {e}")
            
        # fallback
        return [f"{topic} overview", f"{topic} latest news", f"{topic} technical details"]

    async def _synthesize_research(self, topic: str, project_name: str, raw_data: str, depth: str) -> str:
        kind = "deep and exhaustive" if depth == "deep_agentic" else "quick and concise"
        system_prompt = f"""You are ASTA, an autonomous AI researcher synthesizing data on '{topic}' for the '{project_name}' project.
Using the following raw web scraped data, produce a {kind}, highly structured Markdown report.
Format:
# Research: {topic.title()}
## Executive Summary
## Key Findings & Details
## Sources / References (if URLs provided)

Stay strictly factual. Ignore irrelevant boilerplate from the scraped text."""

        # Truncate raw data if it's monstrously huge (Groq max limit safety)
        # Deep agentic 3 queries * 2 results * 3000 chars = 18000 chars. Groq 8k handles ~32k chars safely.
        safe_raw_data = raw_data[:28000]

        try:
            stream = await self.groq_client.chat.completions.create(
                model=self.reasoning_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"RAW DATA:\n{safe_raw_data}"}
                ],
                temperature=0.3,
                max_tokens=3000
            )
            return stream.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[ResearchEngine] Synthesis error: {e}")
            return f"**Synthesis Error:** Could not format report. Raw Data subset:\n{safe_raw_data[:2000]}..."

    async def _save_to_notion(self, executor, session_id: str, project_name: str, topic: str, content: str) -> str:
        """
        Maintains 1 page per project. First queries the DB to see if a page named `project_name` exists.
        If yes -> Append content to it.
        If no -> Create page titled `project_name` and insert content.
        """
        # 1. Query for existing project page
        query_req = ActionRequest(
            session_id=session_id,
            tool_name="notion",
            parameters={
                "operation": "query_database",
                "database": "research"
            },
            intent="Finding existing project page in Notion",
            memory_tag="research_notion_query"
        )
        
        query_res = await executor.execute_action(query_req)
        page_id_to_append = None

        if query_res.status == "success":
            # parse the results to find a page matching the project name
            data = query_res.result
            if isinstance(data, dict) and "data" in data:
                # The generic notion tool might not correctly surface the title if it's named something else.
                # Since the prompt said 1 page per project, we'll iterate the results.
                # Assuming query_database returns something with titles.
                for p in data.get("data", []):
                    title = p.get("title", "")
                    if title.lower().strip() == project_name.lower().strip():
                        page_id_to_append = p.get("id")
                        break

        # 2. Append or Create
        if page_id_to_append:
            logger.info(f"[ResearchEngine] Found existing Notion project page ({page_id_to_append}). Appending...")
            
            # Subheaders to separate topics within the same project page
            formatted_content = f"\n\n---\n\n{content}"
            
            append_req = ActionRequest(
                session_id=session_id,
                tool_name="notion",
                parameters={
                    "operation": "append_to_page",
                    "page_id": page_id_to_append,
                    "content": formatted_content
                },
                intent=f"Appending '{topic}' to '{project_name}' page",
                memory_tag="research_notion_append"
            )
            append_res = await executor.execute_action(append_req)
            return append_res.status
        else:
            logger.info(f"[ResearchEngine] Project page '{project_name}' not found. Creating new page...")
            create_req = ActionRequest(
                session_id=session_id,
                tool_name="notion",
                parameters={
                    "operation": "create_page",
                    "database": "research",
                    "title": project_name,
                    "content": content
                },
                intent=f"Creating '{project_name}' page for '{topic}'",
                memory_tag="research_notion_create"
            )
            create_res = await executor.execute_action(create_req)
            return create_res.status

    async def _generate_spoken_summary(self, topic: str, synthesized_content: str, saved_to_notion: bool) -> str:
        notion_context = "Mention that you've saved the full report to the Research database in Notion under the project's page." if saved_to_notion else "Do NOT mention saving to Notion."
        system_prompt = f"""You are ASTA updating Karthik on research for '{topic}'.
Summarize the main takeaway from the synthesized report in 2-3 short, spoken sentences.
{notion_context}
No markdown, no lists, just natural speech."""

        try:
            stream = await self.groq_client.chat.completions.create(
                model=self.voice_model, 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"REPORT:\n{synthesized_content[:8000]}"}
                ],
                temperature=0.5,
                max_tokens=150
            )
            return stream.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[ResearchEngine] Spoken summary error: {e}")
            return f"I've completed the research on {topic}. " + ("It's saved in your Notion database." if saved_to_notion else "I couldn't save it to Notion, but I have the data.")

# Singleton instance
research_engine = ResearchEngine()