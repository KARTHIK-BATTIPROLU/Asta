"""
ASTA Preferences API
Manage user preferences for LinkedIn, YouTube, Instagram, News, and Routine.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

from backend.app.api.routes import verify_token
from backend.app.services.preferences_service import preferences_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferenceUpdate(BaseModel):
    """Request model for preference updates."""
    updates: Dict[str, Any]


class VoicePreferenceUpdate(BaseModel):
    """Request model for voice-based preference updates."""
    instruction: str


@router.get("/{pref_type}")
async def get_preferences(pref_type: str, token: str = Depends(verify_token)):
    """
    Get current preferences for a specific type.
    
    Valid types: linkedin, youtube, instagram, news, routine, personality
    """
    valid_types = ["linkedin", "youtube", "instagram", "news", "routine", "personality"]
    if pref_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preference type. Must be one of: {', '.join(valid_types)}"
        )
    
    try:
        prefs = await preferences_service.get(pref_type)
        return {
            "type": pref_type,
            "preferences": prefs,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error fetching preferences for {pref_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch preferences: {str(e)}")


@router.put("/{pref_type}")
async def update_preferences(
    pref_type: str,
    update: PreferenceUpdate,
    token: str = Depends(verify_token)
):
    """
    Update preferences for a specific type with direct field updates.
    
    Example body:
    {
        "updates": {
            "tone": "casual and funny",
            "hashtag_count": 7
        }
    }
    """
    valid_types = ["linkedin", "youtube", "instagram", "news", "routine", "personality"]
    if pref_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preference type. Must be one of: {', '.join(valid_types)}"
        )
    
    try:
        success = await preferences_service.update(pref_type, update.updates)
        if success:
            return {
                "status": "updated",
                "type": pref_type,
                "fields": list(update.updates.keys())
            }
        else:
            raise HTTPException(status_code=500, detail="Update failed")
    except Exception as e:
        logger.error(f"Error updating preferences for {pref_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")


@router.post("/{pref_type}/voice")
async def update_preferences_from_voice(
    pref_type: str,
    update: VoicePreferenceUpdate,
    token: str = Depends(verify_token)
):
    """
    Update preferences using natural language instruction.
    
    Example body:
    {
        "instruction": "Make my LinkedIn posts more casual and add more emojis"
    }
    """
    valid_types = ["linkedin", "youtube", "instagram", "news", "routine", "personality"]
    if pref_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preference type. Must be one of: {', '.join(valid_types)}"
        )
    
    try:
        result = await preferences_service.update_from_voice(pref_type, update.instruction)
        return {
            "status": "success",
            "type": pref_type,
            "message": result
        }
    except Exception as e:
        logger.error(f"Error updating preferences from voice for {pref_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")


@router.get("/")
async def list_preference_types(token: str = Depends(verify_token)):
    """List all available preference types."""
    return {
        "preference_types": [
            "linkedin",
            "youtube",
            "instagram",
            "news",
            "routine",
            "personality"
        ],
        "status": "success"
    }
