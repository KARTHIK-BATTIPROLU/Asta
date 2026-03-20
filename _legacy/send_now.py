import sys
import asyncio
from reminder_agent.telegram import telegram_handler

async def send_direct_message(text):
    print(f"🚀 Sending direct message: '{text}'...")
    success = await telegram_handler.send_message(text)
    
    if success:
        print("✅ Message sent successfully!")
    else:
        print("❌ Failed to send message. Check logs/token.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
    else:
        print("Usage: python -m reminder_agent.send_now 'Your message here'")
        message = input("Enter message to send now: ")
    
    if message.strip():
        asyncio.run(send_direct_message(message))
    else:
        print("❌ Error: Message cannot be empty.")