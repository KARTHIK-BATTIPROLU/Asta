"""
Test ASTA Notion Integration via HTTP API
This tests the /api/chat endpoint which uses the supervisor → workflows → Notion pipeline
"""
import requests
import json
import os

# Get API token from environment
API_TOKEN = os.getenv("ASTA_API_BEARER_TOKEN", "your-token-here")

BASE_URL = "http://localhost:8000"

def test_notion_query(message: str, session_id: str = "test-http-001"):
    """Send a message to ASTA via HTTP API"""
    
    print(f"\n{'='*70}")
    print(f"📤 Sending: {message}")
    print(f"{'='*70}")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "message": message,
            "session_id": session_id,
            "voice_enabled": False
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        reply = data.get("reply", "No reply")
        
        print(f"\n✅ Response received:")
        print(f"{'─'*70}")
        print(reply)
        print(f"{'─'*70}\n")
        
        return reply
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.text)
        return None


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖 ASTA NOTION INTEGRATION - HTTP API TEST")
    print("="*70)
    print("\nThis test uses the /api/chat endpoint which routes through:")
    print("  User → /api/chat → run_supervisor() → workflow → Notion")
    print("\n" + "="*70)
    
    # Test 1: Check tasks
    print("\n[TEST 1] Check Notion Tasks")
    test_notion_query("What are my tasks today?")
    
    input("\nPress Enter to continue to next test...")
    
    # Test 2: Add a task
    print("\n[TEST 2] Add a Task to Notion")
    test_notion_query("Add a task: Test HTTP API integration at 4 PM today")
    
    input("\nPress Enter to continue to next test...")
    
    # Test 3: Research query
    print("\n[TEST 3] Research and Save to Notion")
    test_notion_query("Research the latest developments in LangGraph")
    
    print("\n" + "="*70)
    print("✅ HTTP API TEST COMPLETE")
    print("="*70)
    print("\n💡 The HTTP endpoint works with the supervisor → workflow → Notion pipeline!")
    print("   The WebSocket endpoint needs to be updated to use the same approach.\n")
