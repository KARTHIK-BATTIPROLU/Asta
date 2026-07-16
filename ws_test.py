import asyncio
import websockets
import json
import base64
from dotenv import load_dotenv

async def test_client():
    uri = "ws://127.0.0.1:8000/ws/conversation?token=asta-secure-token-2026&device_id=8b7f3a44d045"
    print(f"Connecting to {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Listening for initial orb_state...")
            
            # Wait for idle
            msg = await websocket.recv()
            if isinstance(msg, bytes):
                print("Received binary audio frame of length:", len(msg))
            else:
                print("Received:", msg)
            
            print("\nSending: what's my dog's name")
            # According to pipecat FrameSerializer, a dict with "text" may be recognized as TextFrame,
            # or maybe {"type": "text", "text": "..."}.            print("Sending: what's my dog's name")
            import json
            await websocket.send(json.dumps({"type": "text", "text": "what's my dog's name"}))
            
            # Listen until we get the idle state back
            print("Listening for events...")
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    if isinstance(msg, bytes):
                        print(f"Audio Frame: {len(msg)} bytes")
                    else:
                        print(f"JSON Frame: {msg}")
                        try:
                            import json
                            data = json.loads(msg)
                            if data.get("type") == "orb_state" and data.get("state") == "idle":
                                print("Pipeline returned to idle. Done.")
                                break
                        except Exception:
                            pass
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                    break
    except Exception as e:
        print(f"Connection failed: {e}")

asyncio.run(test_client())
