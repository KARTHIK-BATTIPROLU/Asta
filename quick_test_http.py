"""Quick HTTP API test for Notion integration"""
import requests
import os

API_TOKEN = os.getenv("ASTA_API_BEARER_TOKEN", "")
BASE_URL = "http://localhost:8000"

print("\n" + "="*70)
print("🧪 QUICK HTTP API TEST - Notion Integration")
print("="*70)

# Test: Check tasks
print("\n📤 Asking: 'What are my tasks today?'")
print("-"*70)

response = requests.post(
    f"{BASE_URL}/api/chat",
    headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "message": "What are my tasks today?",
        "session_id": "quick-test-001",
        "voice_enabled": False
    },
    timeout=30
)

if response.status_code == 200:
    data = response.json()
    reply = data.get("reply", "No reply")
    
    print(f"\n✅ Response received ({response.status_code}):")
    print("="*70)
    print(reply)
    print("="*70)
    
    # Check if it mentions tasks or Notion
    if any(word in reply.lower() for word in ["task", "notion", "schedule", "today"]):
        print("\n✅ SUCCESS: Response mentions tasks/Notion!")
    else:
        print("\n⚠️  Response doesn't mention tasks, but API works")
else:
    print(f"\n❌ Error: {response.status_code}")
    print(response.text)

print("\n" + "="*70)
print("Test complete! Server is responding.")
print("="*70 + "\n")
