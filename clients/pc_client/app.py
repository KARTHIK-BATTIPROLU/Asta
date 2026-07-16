import asyncio
import threading
import websockets
import json
import logging
import keyboard
import pystray
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ASTA-PC-Client")

SERVER_URI = "ws://localhost:8000/ws"

class PCClient:
    def __init__(self):
        self.ws = None
        self.running = True
        self.loop = asyncio.new_event_loop()

    def create_icon(self):
        # Generate a simple red icon
        img = Image.new('RGB', (64, 64), color=(20, 20, 20))
        d = ImageDraw.Draw(img)
        d.text((10, 20), "ASTA", fill=(255, 0, 0))
        return img

    async def ws_loop(self):
        while self.running:
            try:
                logger.info(f"Connecting to {SERVER_URI}...")
                async with websockets.connect(SERVER_URI) as ws:
                    self.ws = ws
                    logger.info("Connected.")
                    # Initial wake
                    await ws.send(json.dumps({"t": "text", "text": "PC Client Connected", "client_id": "pc-client-1"}))
                    
                    while self.running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if data.get("t") == "speak":
                            # In Phase 9 MVP, we fallback to printing the TTS
                            logger.info(f"[ASTA Speaking]: {data.get('text')}")
                            # To avoid deadlocks in MVP if server requires ACK:
                            if data.get("requires_ack"):
                                await ws.send(json.dumps({"t": "playback_complete"}))
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WS Connection closed. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"WS Error: {e}")
                await asyncio.sleep(5)

    def on_hotkey(self):
        logger.info("Hotkey pressed. Sending simulated capture to ASTA.")
        if self.ws:
            # We simulate sending a text capture instead of raw audio stream for the MVP
            msg = {"t": "text", "text": "This is a simulated mic input from the PC tray.", "client_id": "pc-client-2"}
            asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(msg)), self.loop)

    def start_background_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ws_loop())

    def run(self):
        # Start WS in background thread
        ws_thread = threading.Thread(target=self.start_background_loop, daemon=True)
        ws_thread.start()

        # Register hotkey
        keyboard.add_hotkey('ctrl+shift+a', self.on_hotkey)
        
        # Setup Tray
        icon = pystray.Icon("ASTA", self.create_icon(), "ASTA Assistant")
        
        def exit_action(icon, item):
            logger.info("Exiting...")
            self.running = False
            icon.stop()
            self.loop.call_soon_threadsafe(self.loop.stop)
            
        icon.menu = pystray.Menu(pystray.MenuItem('Exit', exit_action))
        
        logger.info("Starting Tray Icon. Press Ctrl+Shift+A to trigger ASTA.")
        icon.run()

if __name__ == "__main__":
    client = PCClient()
    client.run()
