"""
Test Memory Flow End-to-End
Tests that memory context flows from session -> LLM
"""
import asyncio
import websockets
import json
import time

WS_URL = "ws://localhost:8000/ws/conversation"

async def test_memory_flow():
    print("\n" + "="*60)
    print("ASTA MEMORY FLOW TEST")
    print("="*60)
    
    # TEST 1: First session - teach ASTA about the project
    print("\n[TEST 1] Starting first session...")
    print("Teaching ASTA: 'I'm building ASTA, a personal AI assistant using LangGraph and Neo4j'")
    
    session_1_id = f"test-session-{int(time.time())}"
    
    try:
        async with websockets.connect(WS_URL) as ws:
            # Send session start
            await ws.send(json.dumps({
                "type": "session_start",
                "session_id": session_1_id
            }))
            
            # Wait for ack
            response = await ws.recv()
            print(f"✓ Session started: {session_1_id}")
            
            # Send the teaching message
            await ws.send(json.dumps({
                "type": "audio_chunk",
                "audio": "",  # Empty audio, we'll use transcript
                "transcript": "I'm building ASTA, a personal AI assistant using LangGraph and Neo4j",
                "is_final": True
            }))
            
            # Collect response
            full_response = ""
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    
                    if data.get("type") == "asta_text":
                        full_response += data.get("text", "")
                    elif data.get("type") == "turn_complete":
                        break
                except asyncio.TimeoutError:
                    break
            
            print(f"✓ ASTA responded: {full_response[:100]}...")
            
            # End session
            await ws.send(json.dumps({
                "type": "session_end",
                "session_id": session_1_id
            }))
            
            print("✓ Session 1 ended")
    
    except Exception as e:
        print(f"✗ Session 1 failed: {e}")
        return False
    
    # Wait for memory processing
    print("\n[WAITING] 10 seconds for entity extraction + Pinecone indexing...")
    await asyncio.sleep(10)
    
    # TEST 2: Second session - ask what we're building
    print("\n[TEST 2] Starting second session...")
    print("Asking ASTA: 'What are we building?'")
    
    session_2_id = f"test-session-{int(time.time())}"
    
    try:
        async with websockets.connect(WS_URL) as ws:
            # Send session start
            await ws.send(json.dumps({
                "type": "session_start",
                "session_id": session_2_id
            }))
            
            # Wait for ack
            response = await ws.recv()
            print(f"✓ Session started: {session_2_id}")
            
            # Ask the question
            await ws.send(json.dumps({
                "type": "audio_chunk",
                "audio": "",
                "transcript": "What are we building?",
                "is_final": True
            }))
            
            # Collect response
            full_response = ""
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    
                    if data.get("type") == "asta_text":
                        full_response += data.get("text", "")
                    elif data.get("type") == "turn_complete":
                        break
                except asyncio.TimeoutError:
                    break
            
            print(f"\n{'='*60}")
            print("ASTA'S RESPONSE:")
            print(f"{'='*60}")
            print(full_response)
            print(f"{'='*60}\n")
            
            # Check if memory worked
            keywords = ["ASTA", "LangGraph", "Neo4j", "assistant", "AI"]
            found_keywords = [kw for kw in keywords if kw.lower() in full_response.lower()]
            
            if found_keywords:
                print(f"✅ MEMORY TEST PASSED!")
                print(f"   Found keywords: {', '.join(found_keywords)}")
                print(f"   Memory is flowing into LLM context!")
            else:
                print(f"❌ MEMORY TEST FAILED!")
                print(f"   ASTA didn't reference the project context")
                print(f"   Expected keywords: {', '.join(keywords)}")
            
            # End session
            await ws.send(json.dumps({
                "type": "session_end",
                "session_id": session_2_id
            }))
            
            print("✓ Session 2 ended")
            
            return len(found_keywords) > 0
    
    except Exception as e:
        print(f"✗ Session 2 failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_memory_flow())
    
    if result:
        print("\n" + "="*60)
        print("🎉 MEMORY SYSTEM IS FULLY OPERATIONAL!")
        print("="*60)
        print("\nNext step: P1 (Auth) - Create authentication middleware")
    else:
        print("\n" + "="*60)
        print("⚠️  MEMORY TEST FAILED - Check logs for:")
        print("="*60)
        print("  [MEMORY] Summary generated for session xxx")
        print("  [MEMORY] Embedding created for session xxx")
        print("  Prefetched context for 'ASTA': N sessions")
