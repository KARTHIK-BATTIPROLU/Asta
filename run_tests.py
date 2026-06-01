"""Simple test runner that outputs to file"""
import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test_imports():
    """Test core imports"""
    tests = [
        ("Auth Middleware", "backend.app.auth.middleware"),
        ("State Schemas", "backend.app.core.state"),
        ("LLM Router", "backend.app.core.llm_router"),
        ("Supervisor", "backend.app.core.supervisor"),
        ("Notion Service", "backend.app.services.notion_service"),
        ("Research Service", "backend.app.services.research_service"),
        ("Weather Service", "backend.app.services.weather_service"),
        ("Sheets Service", "backend.app.services.sheets_service"),
        ("Image Service", "backend.app.services.image_service"),
        ("Scheduler Service", "backend.app.services.scheduler_service"),
        ("Preferences Service", "backend.app.services.preferences_service"),
        ("L1 Cache Service", "backend.app.services.l1_cache"),
        ("Routine Graph", "backend.app.workflows.routine_graph"),
        ("Research Graph", "backend.app.workflows.research_graph"),
        ("LinkedIn Graph", "backend.app.workflows.linkedin_graph"),
        ("YouTube Graph", "backend.app.workflows.youtube_graph"),
        ("Instagram Graph", "backend.app.workflows.instagram_graph"),
        ("Habit Graph", "backend.app.workflows.habit_graph"),
        ("Memory Engine", "memory.memory_engine"),
        ("API Routes", "backend.app.api.routes"),
        ("Preferences API", "backend.app.api.preferences"),
        ("Content API", "backend.app.api.content"),
        ("Health API", "backend.app.api.health"),
    ]
    
    passed = 0
    failed = 0
    results = []
    
    for name, module_path in tests:
        try:
            __import__(module_path)
            results.append(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            results.append(f"[FAIL] {name}: {str(e)[:80]}")
            failed += 1
    
    return passed, failed, results

async def main():
    print("Running ASTA verification tests...")
    
    passed, failed, results = await test_imports()
    
    # Write to file
    with open("test_results.txt", "w", encoding="utf-8") as f:
        f.write("ASTA Implementation Test Results\n")
        f.write("=" * 60 + "\n\n")
        
        for result in results:
            f.write(result + "\n")
        
        f.write("\n" + "=" * 60 + "\n")
        f.write(f"Total: {passed + failed}\n")
        f.write(f"Passed: {passed}\n")
        f.write(f"Failed: {failed}\n")
        f.write(f"Success Rate: {passed / (passed + failed) * 100:.1f}%\n")
    
    print(f"\nResults written to test_results.txt")
    print(f"Passed: {passed}/{passed + failed} ({passed / (passed + failed) * 100:.1f}%)")
    
    return passed, failed

if __name__ == "__main__":
    asyncio.run(main())
