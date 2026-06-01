"""
ASTA Integration Tests
Tests live API endpoints
"""

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"
TOKEN = os.getenv("ASTA_API_BEARER_TOKEN", "test-token-123")

def test_health():
    """Test basic health endpoint"""
    print("\n1. Testing Health Endpoint...")
    response = requests.get(f"{BASE_URL}/api/health/")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    return response.status_code == 200

def test_auth():
    """Test authentication"""
    print("\n2. Testing Authentication...")
    
    # Test with token
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/me", headers=headers)
    print(f"   With token - Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   Response: {response.json()}")
    
    # Test without token
    response_no_auth = requests.get(f"{BASE_URL}/api/me")
    print(f"   Without token - Status: {response_no_auth.status_code}")
    
    return response.status_code == 200 and response_no_auth.status_code == 401

def test_deep_health():
    """Test deep health check"""
    print("\n3. Testing Deep Health Check...")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/health/deep", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Services:")
        for service, status in data.get("services", {}).items():
            print(f"     - {service}: {status.get('status', 'unknown')}")
    return response.status_code == 200

def test_memory_health():
    """Test memory layer health"""
    print("\n4. Testing Memory Layer Health...")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/health/memory", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Memory Layers:")
        for layer, status in data.items():
            if isinstance(status, dict):
                print(f"     - {layer}: {status.get('status', 'unknown')}")
    return response.status_code == 200

def test_preferences():
    """Test preferences API"""
    print("\n5. Testing Preferences API...")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Get LinkedIn preferences
    response = requests.get(f"{BASE_URL}/api/preferences/linkedin", headers=headers)
    print(f"   GET preferences - Status: {response.status_code}")
    if response.status_code == 200:
        prefs = response.json()
        print(f"   Tone: {prefs.get('tone', 'N/A')}")
    
    return response.status_code == 200

def test_content_calendar():
    """Test content calendar"""
    print("\n6. Testing Content Calendar...")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Get LinkedIn calendar
    response = requests.get(f"{BASE_URL}/api/content/calendar/linkedin", headers=headers)
    print(f"   GET calendar - Status: {response.status_code}")
    if response.status_code == 200:
        topics = response.json()
        print(f"   Topics count: {len(topics)}")
        if topics:
            print(f"   First topic: {topics[0].get('topic', 'N/A')[:50]}...")
    
    return response.status_code == 200

def test_chat_endpoint():
    """Test chat endpoint"""
    print("\n7. Testing Chat Endpoint...")
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "message": "hello",
        "session_id": "integration-test-1"
    }
    
    response = requests.post(f"{BASE_URL}/api/chat", headers=headers, json=payload)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Response preview: {data.get('asta_response', '')[:100]}...")
    
    return response.status_code == 200

def test_scheduler_health():
    """Test scheduler health"""
    print("\n8. Testing Scheduler Health...")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/health/scheduler", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Scheduler running: {data.get('scheduler_running', False)}")
        jobs = data.get('jobs', [])
        print(f"   Jobs count: {len(jobs)}")
        for job in jobs:
            print(f"     - {job.get('id', 'unknown')}: {job.get('next_run_time', 'N/A')}")
    return response.status_code == 200

def main():
    print("="*60)
    print("ASTA Integration Tests")
    print("="*60)
    
    tests = [
        ("Health Endpoint", test_health),
        ("Authentication", test_auth),
        ("Deep Health Check", test_deep_health),
        ("Memory Layer Health", test_memory_health),
        ("Preferences API", test_preferences),
        ("Content Calendar", test_content_calendar),
        ("Chat Endpoint", test_chat_endpoint),
        ("Scheduler Health", test_scheduler_health),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                print(f"   ✓ {name} PASSED")
                passed += 1
            else:
                print(f"   ✗ {name} FAILED")
                failed += 1
        except Exception as e:
            print(f"   ✗ {name} ERROR: {str(e)[:100]}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")
    print("="*60)

if __name__ == "__main__":
    main()
