import os
import sys
import asyncio
from dotenv import load_dotenv

# Load .env
load_dotenv()

REQUIRED_VARS = [
    "GROQ_API_KEY",
    "DEEPGRAM_API_KEY",
    "MONGO_URI",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID"
]

def check_env():
    print("--- STEP 1: ENV VALIDATION ---")
    missing = []
    for var in REQUIRED_VARS:
        val = os.getenv(var)
        if not val or val.strip() == "":
            missing.append(var)
        else:
            # Mask key for printing
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "****"
            print(f"✅ {var}: Found ({masked})")
    
    if missing:
        print(f"❌ MISSING VARIABLES: {', '.join(missing)}")
        return False
    
    print("✅ ENV OK: All keys exist")
    return True

from reminder_agent.telegram import telegram_handler

async def test_telegram():
    print("\n--- STEP 2: TELEGRAM TEST ---")
    print(f"Target Chat ID: {os.getenv('TELEGRAM_CHAT_ID')}")
    try:
        success = await telegram_handler.send_message("ASTA SYSTEM TEST 🚀")
        if success:
            print("✅ Telegram Message SENT")
            return True
        else:
            print("❌ Telegram Message FAILED (Check logs)")
            return False
    except Exception as e:
        print(f"❌ Telegram Exception: {e}")
        return False

async def main():
    if not check_env():
        sys.exit(1)
    
    if not await test_telegram():
        sys.exit(1)
        
    print("\n🎉 STEPS 1 & 2 PASSED")

if __name__ == "__main__":
    asyncio.run(main())