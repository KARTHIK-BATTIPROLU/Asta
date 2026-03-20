import asyncio
import sys

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from .config import config, logger
from .mongo import mongo_handler
from .telegram import telegram_handler

async def process_reminders():
    """
    Minimal polling logic.
    """
    logger.info("Polling...")

    # 0. Recover stale reminders
    mongo_handler.recover_stale_reminders()

    # 1. Get due tasks (pending & remind_at <= now)
    reminders = mongo_handler.get_due_reminders()
    
    if reminders:
        logger.info(f"Found {len(reminders)} reminders")

    for reminder in reminders:
        reminder_id = str(reminder["_id"])
        
        # 1. Claim Reminder (Atomicity Check)
        claimed = mongo_handler.claim_reminder(reminder_id)
        if not claimed:
            logger.warning(f"Skipping reminder {reminder_id}: Could not claim (already processing?).")
            continue

        text = reminder.get("text", "Reminder!")
        logger.info(f"Processing reminder ID: {reminder_id}")
        logger.info(f"Sending reminder: {text}")

        # 2. Send Telegram
        try:
            logger.info(f"Invoking telegram_handler.send_message for {reminder_id}")
            success = await telegram_handler.send_message(text)
            
            if success:
                logger.info("Sent successfully")
                
                # 3. Mark Completed
                mongo_handler.mark_completed(reminder_id)
                logger.info("Marked completed")
            else:
                logger.error(f"Failed to send reminder {reminder_id}")
                mongo_handler.fail_reminder(reminder_id)
        except Exception as e:
            logger.error(f"Exception during sending for {reminder_id}: {e}")
            mongo_handler.fail_reminder(reminder_id)

async def main_loop():
    """
    Infinite loop for the agent.
    """
    config.validate()
    logger.info("Reminder Agent Started")
    
    while True:
        try:
            await process_reminders()
        except Exception as e:
            logger.error(f"Critical error in main loop: {e}")
        
        # Sleep
        await asyncio.sleep(config.POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Stopped by user")