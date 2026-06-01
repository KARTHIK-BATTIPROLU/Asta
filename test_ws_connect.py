"""Simple WebSocket connection test"""
import asyncio
import websockets

async def test_connect():
    try:
        async with websockets.connect("ws://localhost:8000/ws/conversation") as ws:
            print("✓ Connected successfully!")
            await ws.close()
    except Exception as e:
        print(f"✗ Connection failed: {e}")

asyncio.run(test_connect())
