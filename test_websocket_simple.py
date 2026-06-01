"""Simple WebSocket connection test"""
import asyncio
import websockets

async def test():
    try:
        print("Attempting to connect to ws://localhost:8000/ws/conversation")
        async with websockets.connect("ws://localhost:8000/ws/conversation") as ws:
            print("✅ CONNECTED!")
            msg = await ws.recv()
            print(f"Received: {msg}")
    except Exception as e:
        print(f"❌ Failed: {e}")
        print("\nTrying with query param...")
        try:
            async with websockets.connect("ws://localhost:8000/ws/conversation?api_key=") as ws:
                print("✅ CONNECTED with query param!")
                msg = await ws.recv()
                print(f"Received: {msg}")
        except Exception as e2:
            print(f"❌ Also failed: {e2}")

asyncio.run(test())
