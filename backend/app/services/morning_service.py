"""
ASTA Morning Service
Compiles the 5-minute morning brief and awake verification questions.
"""
import logging
from datetime import datetime, timedelta, timezone

from backend.app.services.weather_service import weather_service
from backend.app.services.news_service import news_service
from backend.app.services.notion_service import NotionService
from backend.app.db.database import db_manager
from backend.app.core.llm_factory import llm_factory
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

class MorningService:
    def __init__(self):
        self.notion_service = NotionService()

    async def generate_5_minute_brief(self) -> str:
        """
        Prepared at 05:00: weather -> 2-3 tech/AI headlines -> 
        yesterday's incomplete from Notion -> today's commitments from Notion -> priority focus.
        """
        logger.info("[MorningService] Generating 5-minute brief...")
        
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")
        
        # 1. Weather
        weather_summary = await weather_service.get_weather_brief()
        
        # 2. News
        news_summary = await news_service.get_morning_headlines()
        
        # 3. Notion Tasks
        yesterdays_tasks = await self.notion_service.get_pending_tasks(yesterday)
        todays_tasks = await self.notion_service.get_pending_tasks(today)
        
        # 4. Compile block
        brief = []
        brief.append(f"Good morning Karthik. Here is your 5-minute brief.")
        brief.append(f"Weather: {weather_summary}")
        brief.append(f"\nNews Updates:\n{news_summary}")
        
        if yesterdays_tasks:
            brief.append("\nYesterday's incomplete tasks:")
            for t in yesterdays_tasks:
                brief.append(f"- {t['task_name']}")
                
        if todays_tasks:
            brief.append("\nToday's commitments:")
            for t in todays_tasks:
                brief.append(f"- {t['task_name']}")
                
        # Priority focus mock
        brief.append("\nFocus suggestion: Boss, jogging's behaved score is bleeding — today's the day.")
        
        return "\n".join(brief)

    async def generate_awake_verification(self) -> str:
        """
        Generate 2-3 questions ONLY answerable if awake and thinking, 
        generated from yesterday's memory.
        """
        logger.info("[MorningService] Generating awake verification questions...")
        
        if db_manager.db is None:
            return "What did you work on yesterday?"
            
        insights_collection = db_manager.db["insights"]
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        
        # Fetch yesterday's insights
        cursor = insights_collection.find({"ts": {"$gte": yesterday}})
        insights = await cursor.to_list(length=20)
        
        if not insights:
            return "What are your top three priorities for today?"
            
        memory_text = "\n".join([f"- {i['text']}" for i in insights])
        
        prompt_template = """
        You are ASTA, generating awake verification questions for Karthik.
        Based on these memories from yesterday:
        {memory_text}
        
        Generate exactly 2 quick questions to test if he is awake and remembers yesterday.
        Make them specific. For example: "What did you decide about the gateway auth last night?"
        Output ONLY the questions.
        """
        
        prompt = PromptTemplate(template=prompt_template, input_variables=["memory_text"])
        formatted = prompt.format(memory_text=memory_text)
        
        try:
            llm = llm_factory.get_model("extraction")
            result = await llm.ainvoke(formatted)
            questions = result.content.strip()
            return questions
        except Exception as e:
            logger.error(f"[MorningService] Failed to generate questions: {e}")
            return "What are the three things on your plate today?"

morning_service = MorningService()
