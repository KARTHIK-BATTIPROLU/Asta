"""
ASTA Memory Layer - Phoenix Test
────────────────────────────────

Verifies cross-session memory durability and dynamic Neo4j relationships.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from memory import memory_engine
from memory.l2_graph import l2_graph

async def run_phoenix_test():
    print("=== ASTA Memory Layer: Phoenix Test ===\n")
    
    print("1. Connecting all layers...")
    await memory_engine.connect_all()
    
    # ── Session A: Discussing Phoenix & Rust ──
    print("\n2. Simulating Session A (Discussing Project Phoenix and Rust)...")
    session_a_id = "phoenix-session-001"
    messages_a = [
        {"role": "user", "content": "I'm starting a new project called Phoenix. We will be using Rust for the backend to ensure memory safety."},
        {"role": "assistant", "content": "Project Phoenix sounds exciting! Rust is a great choice for memory safety and performance."},
        {"role": "user", "content": "Yeah, I'm currently working on it and I'm very interested in learning more advanced Rust patterns."},
        {"role": "assistant", "content": "I can help you with advanced Rust patterns as you build Project Phoenix."},
    ]
    
    await memory_engine.save_session(
        session_id=session_a_id,
        workflow_type="research",
        messages=messages_a,
        start_time="2026-07-04T10:00:00"
    )
    
    await asyncio.sleep(2) # Allow Neo4j & Pinecone writes to settle
    
    # ── Verify Neo4j Relationships ──
    print("\n3. Verifying dynamic Neo4j relationships...")
    async with l2_graph.driver.session() as session:
        # Check Project Phoenix
        query_project = """
        MATCH (u:User {name: "Karthik"})-[r]->(e:Project {name: "Phoenix"})
        RETURN type(r) as relation
        """
        result = await session.run(query_project)
        record = await result.single()
        if record:
            print(f"   Success! Karthik -[{record['relation']}]-> Phoenix")
        else:
            print("   Failed: Project Phoenix not found or not linked to Karthik.")
            
        # Check Skill Rust
        query_skill = """
        MATCH (u:User {name: "Karthik"})-[r]->(e:Skill {name: "Rust"})
        RETURN type(r) as relation
        """
        result = await session.run(query_skill)
        record = await result.single()
        if record:
            print(f"   Success! Karthik -[{record['relation']}]-> Rust")
        else:
            print("   Failed: Skill Rust not found or not linked to Karthik.")
            
    # ── Session C: Recall ──
    print("\n4. Simulating Session C (Recalling Project Phoenix)...")
    session_c_id = "phoenix-session-002"
    ctx = await memory_engine.get_context_for_session(
        session_id=session_c_id,
        user_input="What was that project I mentioned using Rust?",
        workflow_type="chat"
    )
    
    print(f"   Sessions retrieved: {len(ctx.get('sessions', []))}")
    if ctx.get('sessions'):
        print(f"   Recall Summary: {ctx['sessions'][0].get('summary', '')}")
    else:
        print("   Recall Failed: No sessions retrieved.")
        
    formatted = memory_engine.format_context_for_prompt(ctx)
    if "Phoenix" in formatted and "Rust" in formatted:
        print("   Success! Phoenix and Rust perfectly recalled in prompt context.")
    else:
        print("   Failed to inject Phoenix and Rust into context.")

    print("\n=== Phoenix Test Complete ===")
    await memory_engine.disconnect_all()

if __name__ == "__main__":
    asyncio.run(run_phoenix_test())
