"""
ASTA Preferences Service
Manages user preferences stored in MongoDB.
"""
import logging
import json
import os

logger = logging.getLogger(__name__)


class PreferencesService:
    """Service for managing user preferences."""
    
    async def _get_collection(self):
        """Get preferences collection from MongoDB."""
        from backend.app.db.async_mongo import get_async_db
        db = await get_async_db()
        return db["preferences"]
    
    async def get(self, pref_type: str) -> dict:
        """
        Get preferences by type.
        pref_type: linkedin / youtube / instagram / news / routine / personality
        """
        try:
            col = await self._get_collection()
            doc = await col.find_one({"type": pref_type})
            if not doc:
                doc = await self._load_default(pref_type)
            return {k: v for k, v in doc.items() if k not in ["_id", "type"]}
        except Exception as e:
            logger.error(f"Failed to get preferences for {pref_type}: {e}")
            return {}
    
    async def update(self, pref_type: str, updates: dict) -> bool:
        """Update preferences for a specific type."""
        try:
            col = await self._get_collection()
            await col.update_one(
                {"type": pref_type},
                {"$set": updates},
                upsert=True
            )
            logger.info(f"Updated {pref_type} preferences: {list(updates.keys())}")
            return True
        except Exception as e:
            logger.error(f"Failed to update preferences for {pref_type}: {e}")
            return False
    
    async def update_from_voice(self, pref_type: str, instruction: str) -> str:
        """Parse a natural language update instruction and apply it."""
        try:
            from backend.app.core.llm_router import llm_router
            
            current = await self.get(pref_type)
            result = await llm_router.invoke_with_system(
                "intent_classification",
                f"""Current {pref_type} preferences: {json.dumps(current)}
                
                The user wants to update preferences with this instruction: "{instruction}"
                
                Return ONLY a JSON object with the fields to update. 
                Only include fields that should change. No explanation, just JSON.""",
                instruction
            )
            
            # Parse JSON from LLM response
            raw = result.strip().strip("```json").strip("```").strip()
            updates = json.loads(raw)
            await self.update(pref_type, updates)
            return f"Updated {pref_type} preferences: {', '.join(updates.keys())}"
        except Exception as e:
            logger.error(f"Failed to update preferences from voice: {e}")
            return f"Couldn't parse preference update. Try being more specific, boss."
    
    async def _load_default(self, pref_type: str) -> dict:
        """Load default preferences from JSON file."""
        try:
            default_file = os.path.join(
                os.path.dirname(__file__),
                "..", "..",
                "preferences",
                f"{pref_type}_prefs.json"
            )
            if os.path.exists(default_file):
                with open(default_file) as f:
                    data = json.load(f)
                await self.update(pref_type, data)
                logger.info(f"Loaded default preferences for {pref_type}")
                return data
            logger.warning(f"No default preferences file found for {pref_type}")
            return {}
        except Exception as e:
            logger.error(f"Failed to load default preferences for {pref_type}: {e}")
            return {}


# Global instance
preferences_service = PreferencesService()
