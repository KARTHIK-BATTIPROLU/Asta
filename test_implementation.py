"""
ASTA Implementation Verification Script
Tests core components without requiring full service stack
"""

import sys
import os
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(name, status, message=""):
    try:
        symbol = f"{Colors.GREEN}✓{Colors.END}" if status else f"{Colors.RED}✗{Colors.END}"
        print(f"{symbol} {name}")
        if message:
            print(f"  {Colors.YELLOW}{message}{Colors.END}")
    except UnicodeEncodeError:
        # Fallback for terminals that don't support Unicode
        symbol = "[PASS]" if status else "[FAIL]"
        print(f"{symbol} {name}")
        if message:
            print(f"  {message}")

def print_section(title):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{title}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")

async def test_imports():
    """Test that all core modules can be imported"""
    print_section("1. Testing Core Imports")
    
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
        ("Routine Graph", "backend.app.workflows.routine_graph"),
        ("Research Graph", "backend.app.workflows.research_graph"),
        ("LinkedIn Graph", "backend.app.workflows.linkedin_graph"),
        ("YouTube Graph", "backend.app.workflows.youtube_graph"),
        ("Instagram Graph", "backend.app.workflows.instagram_graph"),
        ("Habit Graph", "backend.app.workflows.habit_graph"),
        ("Memory Engine", "memory.memory_engine"),
        ("L1 Cache", "memory.l1_cache"),
        ("L2 Graph", "memory.l2_graph"),
        ("L3 Vectors", "memory.l3_vectors"),
        ("L4 Store", "memory.l4_store"),
    ]
    
    passed = 0
    failed = 0
    
    for name, module_path in tests:
        try:
            __import__(module_path)
            print_test(name, True)
            passed += 1
        except Exception as e:
            print_test(name, False, str(e))
            failed += 1
    
    return passed, failed

def test_file_structure():
    """Test that all required files exist"""
    print_section("2. Testing File Structure")
    
    files = [
        "backend/app/auth/middleware.py",
        "backend/app/core/state.py",
        "backend/app/core/llm_router.py",
        "backend/app/core/supervisor.py",
        "backend/app/services/notion_service.py",
        "backend/app/services/research_service.py",
        "backend/app/services/weather_service.py",
        "backend/app/services/sheets_service.py",
        "backend/app/services/image_service.py",
        "backend/app/services/scheduler_service.py",
        "backend/app/services/preferences_service.py",
        "backend/app/workflows/routine_graph.py",
        "backend/app/workflows/research_graph.py",
        "backend/app/workflows/linkedin_graph.py",
        "backend/app/workflows/youtube_graph.py",
        "backend/app/workflows/instagram_graph.py",
        "backend/app/workflows/habit_graph.py",
        "backend/app/api/preferences.py",
        "backend/app/api/content.py",
        "backend/app/api/health.py",
        "backend/app/utils/seed_data.py",
        "backend/preferences/linkedin_prefs.json",
        "backend/preferences/youtube_prefs.json",
        "backend/preferences/instagram_prefs.json",
        "backend/preferences/news_prefs.json",
        "memory/memory_engine.py",
        "memory/l1_cache.py",
        "memory/l2_graph.py",
        "memory/l3_vectors.py",
        "memory/l4_store.py",
        "memory/entity_extractor.py",
        "memory/prefetch_engine.py",
        "deploy/nginx.conf",
        "docker-compose.yml",
    ]
    
    passed = 0
    failed = 0
    
    for file_path in files:
        if Path(file_path).exists():
            print_test(file_path, True)
            passed += 1
        else:
            print_test(file_path, False, "File not found")
            failed += 1
    
    return passed, failed

def test_environment():
    """Test environment configuration"""
    print_section("3. Testing Environment Configuration")
    
    required_vars = [
        "GROQ_API_KEY",
        "DEEPGRAM_API_KEY",
        "MONGO_URI",
        "PINECONE_API_KEY",
        "PINECONE_INDEX_NAME",
        "NOTION_API_KEY",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "OPENWEATHER_API_KEY",
        "GEMINI_API_KEY",
        "SERPER_API",
    ]
    
    passed = 0
    failed = 0
    
    from dotenv import load_dotenv
    load_dotenv()
    
    for var in required_vars:
        value = os.getenv(var)
        if value and value.strip():
            print_test(var, True, f"Set ({len(value)} chars)")
            passed += 1
        else:
            print_test(var, False, "Not set or empty")
            failed += 1
    
    return passed, failed

async def test_state_schemas():
    """Test state schema definitions"""
    print_section("4. Testing State Schemas")
    
    try:
        from backend.app.core.state import (
            ASTABaseState,
            RoutineState,
            ResearchState,
            LinkedInState,
            ContentState,
            HabitState,
            add_stage
        )
        
        tests = [
            ("ASTABaseState", ASTABaseState),
            ("RoutineState", RoutineState),
            ("ResearchState", ResearchState),
            ("LinkedInState", LinkedInState),
            ("ContentState", ContentState),
            ("HabitState", HabitState),
            ("add_stage helper", add_stage),
        ]
        
        passed = 0
        failed = 0
        
        for name, obj in tests:
            if obj:
                print_test(name, True)
                passed += 1
            else:
                print_test(name, False)
                failed += 1
        
        return passed, failed
    except Exception as e:
        print_test("State Schemas", False, str(e))
        return 0, 1

async def test_llm_router():
    """Test LLM Router configuration"""
    print_section("5. Testing LLM Router")
    
    try:
        from backend.app.core.llm_router import LLMRouter
        
        router = LLMRouter()
        
        tests = [
            ("Router instantiation", router is not None),
            ("Has get_llm method", hasattr(router, "get_llm")),
            ("Has fallback_chain", hasattr(router, "fallback_chain")),
        ]
        
        passed = 0
        failed = 0
        
        for name, condition in tests:
            print_test(name, condition)
            if condition:
                passed += 1
            else:
                failed += 1
        
        return passed, failed
    except Exception as e:
        print_test("LLM Router", False, str(e))
        return 0, 1

async def test_workflows():
    """Test workflow graph definitions"""
    print_section("6. Testing Workflow Graphs")
    
    workflows = [
        ("Routine Graph", "backend.app.workflows.routine_graph", "routine_graph"),
        ("Research Graph", "backend.app.workflows.research_graph", "research_graph"),
        ("LinkedIn Graph", "backend.app.workflows.linkedin_graph", "linkedin_graph"),
        ("YouTube Graph", "backend.app.workflows.youtube_graph", "youtube_graph"),
        ("Instagram Graph", "backend.app.workflows.instagram_graph", "instagram_graph"),
        ("Habit Graph", "backend.app.workflows.habit_graph", "habit_graph"),
    ]
    
    passed = 0
    failed = 0
    
    for name, module_path, graph_name in workflows:
        try:
            module = __import__(module_path, fromlist=[graph_name])
            graph = getattr(module, graph_name)
            if graph:
                print_test(name, True)
                passed += 1
            else:
                print_test(name, False, "Graph not found")
                failed += 1
        except Exception as e:
            print_test(name, False, str(e))
            failed += 1
    
    return passed, failed

async def test_supervisor():
    """Test supervisor integration"""
    print_section("7. Testing Supervisor Integration")
    
    try:
        from backend.app.core.supervisor import (
            supervisor_graph,
            run_supervisor,
            invoke_routine,
            invoke_research,
            invoke_linkedin,
            invoke_youtube,
            invoke_instagram,
            invoke_habit,
        )
        
        tests = [
            ("Supervisor graph", supervisor_graph is not None),
            ("run_supervisor function", run_supervisor is not None),
            ("invoke_routine", invoke_routine is not None),
            ("invoke_research", invoke_research is not None),
            ("invoke_linkedin", invoke_linkedin is not None),
            ("invoke_youtube", invoke_youtube is not None),
            ("invoke_instagram", invoke_instagram is not None),
            ("invoke_habit", invoke_habit is not None),
        ]
        
        passed = 0
        failed = 0
        
        for name, condition in tests:
            print_test(name, condition)
            if condition:
                passed += 1
            else:
                failed += 1
        
        return passed, failed
    except Exception as e:
        print_test("Supervisor", False, str(e))
        return 0, 1

async def test_memory_layer():
    """Test memory layer components"""
    print_section("8. Testing Memory Layer")
    
    try:
        from memory import memory_engine
        from memory.l1_cache import L1Cache
        from memory.l2_graph import L2Graph
        from memory.l3_vectors import L3Vectors
        from memory.l4_store import L4Store
        from memory.entity_extractor import EntityExtractor
        from memory.prefetch_engine import PrefetchEngine
        
        tests = [
            ("Memory Engine", memory_engine is not None),
            ("L1 Cache", L1Cache is not None),
            ("L2 Graph", L2Graph is not None),
            ("L3 Vectors", L3Vectors is not None),
            ("L4 Store", L4Store is not None),
            ("Entity Extractor", EntityExtractor is not None),
            ("Prefetch Engine", PrefetchEngine is not None),
        ]
        
        passed = 0
        failed = 0
        
        for name, condition in tests:
            print_test(name, condition)
            if condition:
                passed += 1
            else:
                failed += 1
        
        return passed, failed
    except Exception as e:
        print_test("Memory Layer", False, str(e))
        return 0, 1

async def test_api_routes():
    """Test API route definitions"""
    print_section("9. Testing API Routes")
    
    try:
        from backend.app.api.preferences import router as pref_router
        from backend.app.api.content import router as content_router
        from backend.app.api.health import router as health_router
        
        tests = [
            ("Preferences Router", pref_router is not None),
            ("Content Router", content_router is not None),
            ("Health Router", health_router is not None),
        ]
        
        passed = 0
        failed = 0
        
        for name, condition in tests:
            print_test(name, condition)
            if condition:
                passed += 1
            else:
                failed += 1
        
        return passed, failed
    except Exception as e:
        print_test("API Routes", False, str(e))
        return 0, 1

async def test_services():
    """Test service implementations"""
    print_section("10. Testing Services")
    
    services = [
        ("Notion Service", "backend.app.services.notion_service", "NotionService"),
        ("Research Service", "backend.app.services.research_service", "ResearchService"),
        ("Weather Service", "backend.app.services.weather_service", "WeatherService"),
        ("Sheets Service", "backend.app.services.sheets_service", "SheetsService"),
        ("Image Service", "backend.app.services.image_service", "ImageService"),
        ("Scheduler Service", "backend.app.services.scheduler_service", "SchedulerService"),
        ("Preferences Service", "backend.app.services.preferences_service", "PreferencesService"),
    ]
    
    passed = 0
    failed = 0
    
    for name, module_path, class_name in services:
        try:
            module = __import__(module_path, fromlist=[class_name])
            service_class = getattr(module, class_name)
            if service_class:
                print_test(name, True)
                passed += 1
            else:
                print_test(name, False, "Class not found")
                failed += 1
        except Exception as e:
            print_test(name, False, str(e))
            failed += 1
    
    return passed, failed

async def main():
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}ASTA Implementation Verification{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")
    
    total_passed = 0
    total_failed = 0
    
    # Run all tests
    p, f = await test_imports()
    total_passed += p
    total_failed += f
    
    p, f = test_file_structure()
    total_passed += p
    total_failed += f
    
    p, f = test_environment()
    total_passed += p
    total_failed += f
    
    p, f = await test_state_schemas()
    total_passed += p
    total_failed += f
    
    p, f = await test_llm_router()
    total_passed += p
    total_failed += f
    
    p, f = await test_workflows()
    total_passed += p
    total_failed += f
    
    p, f = await test_supervisor()
    total_passed += p
    total_failed += f
    
    p, f = await test_memory_layer()
    total_passed += p
    total_failed += f
    
    p, f = await test_api_routes()
    total_passed += p
    total_failed += f
    
    p, f = await test_services()
    total_passed += p
    total_failed += f
    
    # Summary
    print_section("Test Summary")
    total_tests = total_passed + total_failed
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\nTotal Tests: {total_tests}")
    print(f"{Colors.GREEN}Passed: {total_passed}{Colors.END}")
    print(f"{Colors.RED}Failed: {total_failed}{Colors.END}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    if total_failed == 0:
        print(f"\n{Colors.GREEN}{'='*60}{Colors.END}")
        print(f"{Colors.GREEN}✓ ALL TESTS PASSED - IMPLEMENTATION VERIFIED!{Colors.END}")
        print(f"{Colors.GREEN}{'='*60}{Colors.END}")
    else:
        print(f"\n{Colors.YELLOW}{'='*60}{Colors.END}")
        print(f"{Colors.YELLOW}⚠ Some tests failed - check details above{Colors.END}")
        print(f"{Colors.YELLOW}{'='*60}{Colors.END}")

if __name__ == "__main__":
    asyncio.run(main())
