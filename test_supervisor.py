"""
Test the Supervisor Graph
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.app.core.supervisor import run_supervisor


async def test_supervisor():
    print("\n" + "="*60)
    print("ASTA SUPERVISOR TEST")
    print("="*60)
    
    # Test 1: Simple chat
    print("\n[TEST 1] Simple Chat")
    print("Input: 'Hey ASTA, what's up?'")
    result = await run_supervisor(
        session_id="test-chat-001",
        user_input="Hey ASTA, what's up?"
    )
    print(f"Workflow: {result['workflow_type']}")
    print(f"Response: {result['asta_response'][:200]}...")
    
    # Test 2: Research intent
    print("\n[TEST 2] Research Intent")
    print("Input: 'Research the latest developments in quantum computing'")
    result = await run_supervisor(
        session_id="test-research-001",
        user_input="Research the latest developments in quantum computing"
    )
    print(f"Workflow: {result['workflow_type']}")
    print(f"Intent: {result['intent']}")
    print(f"Response: {result['asta_response'][:200]}...")
    
    # Test 3: Routine intent
    print("\n[TEST 3] Routine Intent")
    print("Input: 'What's my day looking like?'")
    result = await run_supervisor(
        session_id="test-routine-001",
        user_input="What's my day looking like?"
    )
    print(f"Workflow: {result['workflow_type']}")
    print(f"Intent: {result['intent']}")
    print(f"Response: {result['asta_response'][:200]}...")
    
    # Test 4: Content intent
    print("\n[TEST 4] Content Intent")
    print("Input: 'Write a LinkedIn post about AI trends'")
    result = await run_supervisor(
        session_id="test-content-001",
        user_input="Write a LinkedIn post about AI trends"
    )
    print(f"Workflow: {result['workflow_type']}")
    print(f"Intent: {result['intent']}")
    print(f"Response: {result['asta_response'][:200]}...")
    
    # Test 5: Memory context (reference previous conversation)
    print("\n[TEST 5] Memory Context Test")
    print("Input: 'What are we building?' (should reference ASTA from memory)")
    result = await run_supervisor(
        session_id="test-memory-001",
        user_input="What are we building?"
    )
    print(f"Workflow: {result['workflow_type']}")
    print(f"Memory context loaded: {len(result.get('memory_context', ''))} chars")
    print(f"Entities mentioned: {result.get('entities_mentioned', [])}")
    print(f"Response: {result['asta_response'][:300]}...")
    
    print("\n" + "="*60)
    print("✅ SUPERVISOR TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_supervisor())
