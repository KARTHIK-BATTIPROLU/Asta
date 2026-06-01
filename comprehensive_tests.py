#!/usr/bin/env python3
"""Comprehensive ASTA Integration Tests"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"
TOKEN = "asta-secure-token-2026"

def print_test(name, passed, details=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {name}")
    if details:
        print(f"      {details}")

def test_1_health():
    """Test basic health endpoint"""
    print("\n=== Test 1: Health Endpoint ===")
    try:
        r = requests.get(f"{BASE_URL}/api/health/", timeout=5)
        passed = r.status_code == 200 and r.json().get("status") == "ok"
        print_test("Basic health check", passed, f"Status: {r.status_code}")
        return passed
    except Exception as e:
        print_test("Basic health check", False, str(e))
        return False

def test_2_auth():
    """Test authentication"""
    print("\n=== Test 2: Authentication ===")
    
    # Test with valid token
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/me", headers=headers, timeout=5)
        valid_token = r.status_code == 200
        print_test("Valid token accepted", valid_token, f"Status: {r.status_code}")
    except Exception as e:
        print_test("Valid token accepted", False, str(e))
        valid_token = False
    
    # Test with invalid token
    try:
        headers = {"Authorization": "Bearer invalid-token"}
        r = requests.get(f"{BASE_URL}/api/me", headers=headers, timeout=5)
        invalid_rejected = r.status_code == 401
        print_test("Invalid token rejected", invalid_rejected, f"Status: {r.status_code}")
    except Exception as e:
        print_test("Invalid token rejected", False, str(e))
        invalid_rejected = False
    
    return valid_token and invalid_rejected

def test_3_deep_health():
    """Test deep health check"""
    print("\n=== Test 3: Deep Health Check ===")
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/health/deep", headers=headers, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            services = data.get("services", {})
            print_test("Deep health check", True, f"Services: {len(services)}")
            
            for service, status in services.items():
                svc_status = status.get("status", "unknown")
                print(f"      - {service}: {svc_status}")
            
            return True
        else:
            print_test("Deep health check", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Deep health check", False, str(e))
        return False

def test_4_memory_health():
    """Test memory layer health"""
    print("\n=== Test 4: Memory Layer Health ===")
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/health/memory", headers=headers, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            print_test("Memory health check", True, f"Layers: {len(data)}")
            
            for layer, status in data.items():
                if isinstance(status, dict):
                    layer_status = status.get("status", "unknown")
                    print(f"      - {layer}: {layer_status}")
            
            return True
        else:
            print_test("Memory health check", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Memory health check", False, str(e))
        return False

def test_5_scheduler():
    """Test scheduler health"""
    print("\n=== Test 5: Scheduler Health ===")
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/health/scheduler", headers=headers, timeout=5)
        
        if r.status_code == 200:
            data = r.json()
            running = data.get("scheduler_running", False)
            jobs = data.get("jobs", [])
            print_test("Scheduler running", running, f"Jobs: {len(jobs)}")
            
            for job in jobs:
                print(f"      - {job.get('id', 'unknown')}: {job.get('next_run_time', 'N/A')}")
            
            return running
        else:
            print_test("Scheduler running", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Scheduler running", False, str(e))
        return False

def test_6_preferences():
    """Test preferences API"""
    print("\n=== Test 6: Preferences API ===")
    
    # Get preferences
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/preferences/linkedin", headers=headers, timeout=5)
        
        if r.status_code == 200:
            prefs = r.json()
            print_test("Get LinkedIn preferences", True, f"Tone: {prefs.get('tone', 'N/A')[:30]}")
            return True
        else:
            print_test("Get LinkedIn preferences", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Get LinkedIn preferences", False, str(e))
        return False

def test_7_content_calendar():
    """Test content calendar"""
    print("\n=== Test 7: Content Calendar ===")
    
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/content/calendar/linkedin", headers=headers, timeout=5)
        
        if r.status_code == 200:
            topics = r.json()
            print_test("Get content calendar", True, f"Topics: {len(topics)}")
            if topics:
                print(f"      First: {topics[0].get('topic', 'N/A')[:50]}...")
            return True
        else:
            print_test("Get content calendar", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Get content calendar", False, str(e))
        return False

def test_8_chat_simple():
    """Test simple chat"""
    print("\n=== Test 8: Chat Endpoint (Simple) ===")
    
    try:
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "message": "hello",
            "session_id": "test-simple-1"
        }
        
        r = requests.post(f"{BASE_URL}/api/chat", headers=headers, json=payload, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            response = data.get("asta_response", "")
            print_test("Simple chat", True, f"Response length: {len(response)} chars")
            print(f"      Preview: {response[:80]}...")
            return True
        else:
            print_test("Simple chat", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Simple chat", False, str(e))
        return False

def test_9_chat_with_hint():
    """Test chat with workflow hint"""
    print("\n=== Test 9: Chat with Workflow Hint ===")
    
    try:
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "message": "what are my tasks today",
            "session_id": "test-routine-1",
            "workflow_hint": "routine"
        }
        
        r = requests.post(f"{BASE_URL}/api/chat", headers=headers, json=payload, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            response = data.get("asta_response", "")
            workflow = data.get("workflow_used", "unknown")
            print_test("Chat with hint", True, f"Workflow: {workflow}")
            print(f"      Response: {response[:80]}...")
            return True
        else:
            print_test("Chat with hint", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("Chat with hint", False, str(e))
        return False

def test_10_llm_health():
    """Test LLM health"""
    print("\n=== Test 10: LLM Health ===")
    
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        r = requests.get(f"{BASE_URL}/api/health/llm", headers=headers, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "unknown")
            print_test("LLM health check", status == "ok", f"Status: {status}")
            return status == "ok"
        else:
            print_test("LLM health check", False, f"Status: {r.status_code}")
            return False
    except Exception as e:
        print_test("LLM health check", False, str(e))
        return False

def main():
    print("="*70)
    print("ASTA COMPREHENSIVE INTEGRATION TESTS")
    print("="*70)
    print(f"Server: {BASE_URL}")
    print(f"Token: {TOKEN[:20]}...")
    
    tests = [
        ("Health Endpoint", test_1_health),
        ("Authentication", test_2_auth),
        ("Deep Health Check", test_3_deep_health),
        ("Memory Layer Health", test_4_memory_health),
        ("Scheduler Health", test_5_scheduler),
        ("Preferences API", test_6_preferences),
        ("Content Calendar", test_7_content_calendar),
        ("Simple Chat", test_8_chat_simple),
        ("Chat with Hint", test_9_chat_with_hint),
        ("LLM Health", test_10_llm_health),
    ]
    
    results = []
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n[ERROR] {name}: {str(e)}")
            results.append((name, False))
            failed += 1
        
        time.sleep(0.5)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print("\n" + "-"*70)
    print(f"Total Tests: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")
    print("="*70)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
    
    return passed, failed

if __name__ == "__main__":
    main()
