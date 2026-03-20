import httpx
from .config import config, logger

class TelegramHandler:
    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, text: str):
        """
        Send a message via Telegram API.
        """
        if not self.token or not self.chat_id:
            logger.error("Cannot send Telegram message: Missing config.")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": f"🔔 {text}" 
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, json=payload, timeout=10.0)
                response.raise_for_status()
                logger.info(f"Telegram sent successfully: {response.json()}")
                return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram API Error: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Telegram Connection Error: {e}")
            return False

    async def send_test_message(self):
        """
        Send a test message to verify Telegram configuration.
        """
        logger.info("Sending test message...")
        success = await self.send_message("ASTA TEST MESSAGE ✅")
        if success:
            logger.info("Telegram Test: SUCCESS ✅")
        else:
            logger.error("Telegram Test: FAILED ❌")
        return success

telegram_handler = TelegramHandler()