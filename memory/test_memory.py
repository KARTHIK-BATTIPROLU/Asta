"""
ASTA Memory Layer E2E Test Script
─────────────────────────────────

End-to-end test script for the memory layer as specified in Step 14.1.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from memory import memory_engine

async def run_test():
    print("=== ASTA Memory Layer E2E Test ===\n")
    
    # Connect all layers
    print("1. Connecting all layers...")
    try:
        status = await memory_engine.connect_all()
        print(f"   Status: {status}\n")
    except Exception as e:
        print(f"   Connection failed: {e}")
        return
    
    # Simulate Session 1: ASTA project discussion
    print("2. Simulating Session 1 (ASTA project)...")
    session1_id = "test-session-001"
    messages_1 = [
        {"role": "user", "content": "Let's work on the ASTA project. I need to implement the memory layer using Neo4j and Pinecone."},
        {"role": "assistant", "content": "Sure boss! Let's build the memory layer for ASTA. We'll use Neo4j for the knowledge graph and Pinecone for vector search."},
        {"role": "user", "content": "I decided to use Redis as the L1 cache. This will make retrieval feel instant."},
        {"role": "assistant", "content": "Great decision! Redis as L1 cache will give you sub-5ms retrieval for hot entities."},
    ]
    
    try:
        saved = await memory_engine.save_session(
            session_id=session1_id,
            workflow_type="research",
            messages=messages_1,
            start_time="2026-04-20T10:00:00"
        )
        print(f"   Session 1 saved: {saved}\n")
    except Exception as e:
        print(f"   Session save failed: {e}\n")
    
    await asyncio.sleep(2)  # Wait for Pinecone to index
    
    # Simulate Session 2: Ask about ASTA memory
    print("3. Simulating Session 2 (retrieving context about ASTA)...")
    session2_id = "test-session-002"
    
    try:
        ctx = await memory_engine.get_context_for_session(
            session_id=session2_id,
            user_input="What was my decision about the ASTA memory layer?",
            workflow_type="research"
        )
        print(f"   Sessions retrieved: {len(ctx['sessions'])}")
        print(f"   Entities spotted: {ctx.get('entities_spotted', [])}")
        if ctx['sessions']:
            print(f"   First session summary: {ctx['sessions'][0].get('summary', '')[:200]}")
        
        # Test formatted context
        formatted = memory_engine.format_context_for_prompt(ctx)
        print(f"\n   Formatted context preview:\n{formatted[:400]}\n")
    except Exception as e:
        print(f"   Context retrieval failed: {e}\n")
    
    # Test permanent memory
    print("4. Testing permanent memory...")
    try:
        doc = await memory_engine.remember(
            "Decided to use Redis L1 cache + Neo4j L2 + Pinecone L3 + MongoDB L4 for memory",
            tags=["ASTA", "architecture", "memory"]
        )
        print(f"   Saved permanent memory: {doc.get('memory_id', 'FAILED')}")
        
        recall = await memory_engine.recall("Redis cache decision")
        print(f"   Recalled: {len(recall)} memories\n")
    except Exception as e:
        print(f"   Permanent memory failed: {e}\n")
    
    # Health check
    print("5. Health check...")
    try:
        health = await memory_engine.health_check()
        print(f"   {health}\n")
    except Exception as e:
        print(f"   Health check failed: {e}\n")
    
    print("=== Test Complete ===")
    await memory_engine.disconnect_all()

if __name__ == "__main__":
    asyncio.run(run_test())