from datetime import datetime, timezone
import dateparser
from langchain_core.tools import tool
import logging
import pytz
from backend.app.db.mongo import MongoDB

logger = logging.getLogger(__name__)

# Define Timezones
ist = pytz.timezone("Asia/Kolkata")
utc = pytz.utc

@tool
def create_reminder(text: str, time: str) -> str:
    """
    Creates a reminder for a specific time.
    Parsing strictness is handled, but the user should provide a clear future time.
    
    Args:
        text: The content/message of the reminder.
        time: The time expression (e.g., "in 10 minutes", "tomorrow at 5pm").
    """
    try:
        # 1. Parse Input (Assume IST)
        # Using dateparser with TIMEZONE='Asia/Kolkata' ensures relative terms like "tomorrow" are calculated in IST
        settings = {
            'TIMEZONE': 'Asia/Kolkata',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future'
        }
        
        parsed_time = dateparser.parse(time, settings=settings)
        
        if not parsed_time:
            return f"I couldn't understand when you want to be reminded for '{text}'. Please provide a clearer time."

        logger.info(f"User time (IST): {parsed_time}")

        # Ensure we have a timezone aware datetime
        # If it was returned aware (IST) great. If naive, assume IST.
        if parsed_time.tzinfo is None:
             parsed_time = ist.localize(parsed_time)
        else:
             # Ensure it is in IST for consistent logging/calc if dateparser returned something else (unlikely with settings)
             parsed_time = parsed_time.astimezone(ist)

        # 2. Convert to UTC for Storage
        utc_time = parsed_time.astimezone(utc)
        logger.info(f"Stored time (UTC): {utc_time}")
            
        now_utc = datetime.now(timezone.utc)
        
        # 6. Validation (Reject Past Times)
        if utc_time < now_utc:
             return f"I can't set a reminder in the past. ({time})"

        reminder_data = {
            "text": text,
            "remind_at": utc_time,
            "status": "pending",
            "created_at": now_utc
        }

        MongoDB.insert_reminder(reminder_data)
        
        # 3. ASTA Response (UTC -> IST)
        ist_time = utc_time.astimezone(ist)
        
        # 4. Response Format
        friendly_time = ist_time.strftime("%A, %d %B at %I:%M %p (IST)")
        return f"Done! I've set a reminder: '{text}' for {friendly_time}."

    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        return "Sorry, I encountered an error while setting the reminder."
