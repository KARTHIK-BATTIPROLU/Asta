"""Test WebSocket connection"""
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/conversation"
    
    print(f"\n{'='*70}")
    print("🧪 Testing WebSocket Connection")
    print(f"{'='*70}")
    print(f"Connecting to: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")
            
            # Wait for ready message
            response = await websocket.recv()
            data = json.loads(response)
            print(f"\n📨 Received: {data}")
            
            if data.get("type") == "ready":
                print("✅ Server is ready!")
                
                # Send session_start
                await websocket.send(json.dumps({
                    "type": "session_start"
                }))
                print("\n📤 Sent: session_start")
                
                # Send a test message
                await websocket.send(json.dumps({
                    "type": "text_input",
                    "text": "Hello ASTA"
                }))
                print("📤 Sent: Hello ASTA")
                
                # Wait for responses
                print("\n📨 Waiting for responses...")
                for i in range(5):
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        data = json.loads(response)
                        print(f"  {i+1}. {data.get('type', 'unknown')}: {str(data)[:100]}")
                    except asyncio.TimeoutError:
                        print(f"  {i+1}. (timeout)")
                        break
                
                print("\n✅ WebSocket is working!")
            
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print("\nPossible issues:")
        print("  1. Server not running")
        print("  2. Port 8000 blocked")
        print("  3. Firewall blocking connection")
    
    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(test_websocket())
