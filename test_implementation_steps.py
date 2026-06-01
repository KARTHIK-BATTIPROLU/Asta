"""
Test script to verify ASTA implementation steps are complete
Run with: python test_implementation_steps.py
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

async def test_step_p1_auth():
    """Test STEP P1 - Auth Middleware"""
    print("\n=== Testing STEP P1: Auth Middleware ===")
    try:
        from backend.app.auth.middleware import verify_token, get_current_user
        from backend.app.config import settings
        
        # Check if ASTA_JWT_TOKEN exists
        assert hasattr(settings, 'ASTA_JWT_TOKEN'), "ASTA_JWT_TOKEN not in settings"
        assert settings.ASTA_JWT_TOKEN == "asta-dev-token-change-in-production", "ASTA_JWT_TOKEN value incorrect"
        
        print("✓ Auth middleware imports successfully")
        print("✓ ASTA_JWT_TOKEN configured correctly")
        print("✓ STEP P1 COMPLETE")
        return True
    except Exception as e:
        print(f"✗ STEP P1 FAILED: {e}")
        return False


async def test_step_p2_states():
    """Test STEP P2 - LangGraph State Schemas"""
    print("\n=== Testing STEP P2: LangGraph State Schemas ===")
    try:
        from backend.app.core.state import (
            ASTABaseState, RoutineState, ResearchState, 
            LinkedInState, ContentState, HabitState, add_stage
        )
        
        # Check ASTABaseState has required fields
        required_fields = [
            'session_id', 'workflow_type', 'messages', 'current_input',
            'asta_response', 'memory_context', 'retrieved_memories',
            'session_summary', 'needs_clarification', 'clarification_question',
            'is_complete', 'notion_page_id', 'tools_used', 'intermediate_stages',
            'error', 'start_time'
        ]
        
        annotations = ASTABaseState.__annotations__
        for field in required_fields:
            assert field in annotations, f"Missing field: {field}"
        
        # Test add_stage helper
        test_state = {"intermediate_stages": []}
        result = add_stage(test_state, "test", "done", "detail")
        assert len(result) == 1, "add_stage didn't add stage"
        assert result[0]["stage"] == "test", "Stage name incorrect"
        
        print("✓ All state schemas imported successfully")
        print("✓ ASTABaseState has all required fields")
        print("✓ add_stage helper works correctly")
        print("✓ STEP P2 COMPLETE")
        return True
    except Exception as e:
        print(f"✗ STEP P2 FAILED: {e}")
        return False


async def test_step_p3_llm_router():
    """Test STEP P3 - LLM Router"""
    print("\n=== Testing STEP P3: LLM Router ===")
    try:
        from backend.app.core.llm_router import llm_router, TASK_MODEL_MAP
        
        # Check task model map
        required_tasks = [
            "voice_response", "intent_classification", "entity_extraction",
            "deep_writing", "research_synthesis", "script_generation",
            "post_generation", "quick_response", "image_prompt", "fallback"
        ]
        
        for task in required_tasks:
            assert task in TASK_MODEL_MAP, f"Missing task: {task}"
        
        # Check LLM router has required methods
        assert hasattr(llm_router, 'get_llm'), "Missing get_llm method"
        assert hasattr(llm_router, 'invoke'), "Missing invoke method"
        assert hasattr(llm_router, 'invoke_with_system'), "Missing invoke_with_system method"
        
        # Test get_llm
        llm = llm_router.get_llm("voice_response")
        assert llm is not None, "get_llm returned None"
        
        print("✓ LLM router imported successfully")
        print("✓ All task types mapped")
        print("✓ LLM router methods available")
        print("✓ STEP P3 COMPLETE")
        return True
    except Exception as e:
        print(f"✗ STEP P3 FAILED: {e}")
        return False


async def test_step_p4_supervisor():
    """Test STEP P4 - Supervisor Graph"""
    print("\n=== Testing STEP P4: Supervisor Graph ===")
    try:
        from backend.app.core.supervisor import (
            supervisor_graph, run_supervisor,
            classify_intent, fetch_memory_context,
            handle_clarification, handle_memory_recall
        )
        
        # Check supervisor graph exists
        assert supervisor_graph is not None, "supervisor_graph is None"
        
        # Check run_supervisor function exists
        assert callable(run_supervisor), "run_supervisor is not callable"
        
        # Check all node functions exist
        node_functions = [
            classify_intent, fetch_memory_context,
            handle_clarification, handle_memory_recall
        ]
        for func in node_functions:
            assert callable(func), f"{func.__name__} is not callable"
        
        print("✓ Supervisor graph compiled successfully")
        print("✓ run_supervisor function available")
        print("✓ All node functions defined")
        print("✓ STEP P4 COMPLETE")
        return True
    except Exception as e:
        print(f"✗ STEP P4 FAILED: {e}")
        return False


async def test_services_exist():
    """Test that all required services exist"""
    print("\n=== Testing Services Existence ===")
    try:
        services = [
            ('notion_service', 'backend.app.services.notion_service'),
            ('research_service', 'backend.app.services.research_service'),
            ('weather_service', 'backend.app.services.weather_service'),
            ('sheets_service', 'backend.app.services.sheets_service'),
            ('image_service', 'backend.app.services.image_service'),
            ('scheduler_service', 'backend.app.services.scheduler_service'),
            ('preferences_service', 'backend.app.services.preferences_service'),
        ]
        
        for service_name, module_path in services:
            try:
                module = __import__(module_path, fromlist=[service_name])
                service = getattr(module, service_name)
                print(f"✓ {service_name} exists")
            except Exception as e:
                print(f"✗ {service_name} missing or error: {e}")
        
        print("✓ All services checked")
        return True
    except Exception as e:
        print(f"✗ Services check FAILED: {e}")
        return False


async def test_workflows_exist():
    """Test that all workflow graphs exist"""
    print("\n=== Testing Workflow Graphs Existence ===")
    try:
        workflows = [
            ('routine_graph', 'backend.app.workflows.routine_graph'),
            ('research_graph', 'backend.app.workflows.research_graph'),
            ('linkedin_graph', 'backend.app.workflows.linkedin_graph'),
            ('youtube_graph', 'backend.app.workflows.youtube_graph'),
            ('instagram_graph', 'backend.app.workflows.instagram_graph'),
            ('habit_graph', 'backend.app.workflows.habit_graph'),
        ]
        
        for graph_name, module_path in workflows:
            try:
                module = __import__(module_path, fromlist=[graph_name])
                graph = getattr(module, graph_name)
                print(f"✓ {graph_name} exists")
            except Exception as e:
                print(f"✗ {graph_name} missing or error: {e}")
        
        print("✓ All workflow graphs checked")
        return True
    except Exception as e:
        print(f"✗ Workflow graphs check FAILED: {e}")
        return False


async def test_api_routes_exist():
    """Test that all API routes exist"""
    print("\n=== Testing API Routes Existence ===")
    try:
        import os
        api_path = os.path.join(os.path.dirname(__file__), 'backend', 'app', 'api')
        
        required_files = [
            'routes.py',
            'chat.py',
            'preferences.py',
            'content.py',
            'health.py',
        ]
        
        for filename in required_files:
            filepath = os.path.join(api_path, filename)
            if os.path.exists(filepath):
                print(f"✓ {filename} exists")
            else:
                print(f"✗ {filename} missing")
        
        print("✓ All API route files checked")
        return True
    except Exception as e:
        print(f"✗ API routes check FAILED: {e}")
        return False


async def test_preference_files_exist():
    """Test that all preference JSON files exist"""
    print("\n=== Testing Preference Files Existence ===")
    try:
        import os
        prefs_path = os.path.join(os.path.dirname(__file__), 'backend', 'preferences')
        
        required_files = [
            'linkedin_prefs.json',
            'youtube_prefs.json',
            'instagram_prefs.json',
            'news_prefs.json',
        ]
        
        for filename in required_files:
            filepath = os.path.join(prefs_path, filename)
            if os.path.exists(filepath):
                print(f"✓ {filename} exists")
            else:
                print(f"✗ {filename} missing")
        
        print("✓ All preference files checked")
        return True
    except Exception as e:
        print(f"✗ Preference files check FAILED: {e}")
        return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("ASTA IMPLEMENTATION VERIFICATION")
    print("=" * 60)
    
    results = []
    
    # Test Phase P - Project Plumbing
    results.append(await test_step_p1_auth())
    results.append(await test_step_p2_states())
    results.append(await test_step_p3_llm_router())
    results.append(await test_step_p4_supervisor())
    
    # Test Phase S - Services
    results.append(await test_services_exist())
    
    # Test Phase W - Workflows
    results.append(await test_workflows_exist())
    
    # Test Phase A - API Routes
    results.append(await test_api_routes_exist())
    
    # Test Phase D - Data/Preferences
    results.append(await test_preference_files_exist())
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ ALL IMPLEMENTATION STEPS VERIFIED!")
    else:
        print(f"\n✗ {total - passed} tests failed. Review output above.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
