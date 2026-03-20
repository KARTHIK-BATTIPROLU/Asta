import asyncio
from reminder_agent.telegram import telegram_handler

async def main():
    await telegram_handler.send_test_message()

if __name__ == "__main__":
    asyncio.run(main())