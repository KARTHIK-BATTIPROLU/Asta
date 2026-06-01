"""Test specific Notion queries"""
import requests
import os
import sys

API_TOKEN = os.getenv("ASTA_API_BEARER_TOKEN", "")
if not API_TOKEN:
    print("❌ ASTA_API_BEARER_TOKEN not set!")
    sys.exit(1)

BASE_URL = "http://localhost:8000"

def test_query(message, test_name):
    print(f"\n{'='*70}")
    print(f"🧪 {test_name}")
    print(f"{'='*70}")
    print(f"📤 Query: {message}")
    print("-"*70)
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "message": message,
            "session_id": f"test-{test_name.lower().replace(' ', '-')}",
            "voice_enabled": False
        },
        timeout=60
    )
    
    if response.status_code == 200:
        data = response.json()
        reply = data.get("reply", "No reply")
        
        print(f"\n✅ Response ({response.status_code}):")
        print("="*70)
        print(reply[:500])
        if len(reply) > 500:
            print("... (truncated)")
        print("="*70)
        return True
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.text[:200])
        return False

print("\n" + "="*70)
print("🤖 ASTA NOTION INTEGRATION - SPECIFIC TESTS")
print("="*70)

# Test 1: List tasks
test_query(
    "Show me all my pending tasks from Notion",
    "TEST 1: List Tasks"
)

input("\nPress Enter for next test...")

# Test 2: Add task
test_query(
    "Add a new task to Notion: Test the integration at 5 PM",
    "TEST 2: Add Task"
)

input("\nPress Enter for next test...")

# Test 3: Morning brief
test_query(
    "Give me my morning briefing",
    "TEST 3: Morning Brief"
)

print("\n" + "="*70)
print("✅ ALL TESTS COMPLETE")
print("="*70 + "\n")
