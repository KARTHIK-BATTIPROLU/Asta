"""
Quick test to verify task creation works without calendar tool
"""
import asyncio
from backend.app.core.supervisor import run_supervisor
from datetime import datetime

async def test_task_creation():
    """Test that task creation routes to Notion, not calendar"""
    
    print("=" * 60)
    print("Testing Task Creation - Calendar Tool Disabled")
    print("=" * 60)
    
    test_cases = [
        "add I have to attend a meet at 8:30 pm today",
        "what are my tasks in routine",
        "schedule a call with John at 3pm",
    ]
    
    for i, user_input in enumerate(test_cases, 1):
        print(f"\n[Test {i}] User: {user_input}")
        print("-" * 60)
        
        try:
            result = await run_supervisor(
                session_id=f"test-{datetime.now().timestamp()}",
                user_input=user_input,
                user_id="karthik"
            )
            
            print(f"Workflow: {result.get('workflow_type')}")
            print(f"Response: {result.get('asta_response')[:200]}...")
            print(f"Tools Used: {result.get('tools_used', [])}")
            
            # Verify calendar tool was NOT used
            tools_used = result.get('tools_used', [])
            if 'calendar' in str(tools_used).lower():
                print("❌ FAIL: Calendar tool was used!")
            else:
                print("✅ PASS: Calendar tool not used")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_task_creation())
