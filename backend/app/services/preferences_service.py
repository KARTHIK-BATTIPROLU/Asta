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
        from backend.app.db.database import db_manager
        db = db_manager.db
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
            from backend.app.core.llm_factory import acomplete

            current = await self.get(pref_type)
            raw = await acomplete(
                system=(
                    f"Current {pref_type} preferences: {json.dumps(current)}\n\n"
                    "The user wants to update their preferences based on the instruction below.\n"
                    "Return ONLY a valid JSON object with the fields to update. "
                    "Include only fields that should change. No explanation, no markdown fences, just JSON."
                ),
                user=instruction,
                task="quick",
                temperature=0.0,
                max_tokens=300,
            )
            # Strip markdown fences if the LLM wraps the JSON
            raw = (raw or "").strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            updates = json.loads(raw)
            await self.update(pref_type, updates)
            return f"Updated {pref_type} preferences: {', '.join(str(k) for k in updates.keys())}"
        except Exception as e:
            logger.error(f"Failed to update preferences from voice: {e}")
            return "Couldn't parse preference update. Try being more specific, boss."
    
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
