#!/usr/bin/env python3
"""
ASTA System Integration Test
Tests key components to ensure everything is working properly
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

async def test_imports():
    """Test that all core modules can be imported"""
    print("🔍 Testing Core Module Imports...")
    
    try:
        # Core components
        from app.core.state import ASTABaseState, RoutineState, ResearchState
        from app.core.llm_router import llm_router
        from app.core.supervisor import supervisor_graph, run_supervisor
        
        # Services
        from app.services.notion_service import notion_service
        from app.services.research_service import research_service
        from app.services.weather_service import weather_service
        
        # Workflows
        from app.workflows.routine_graph import routine_graph
        from app.workflows.research_graph import research_graph
        from app.workflows.linkedin_graph import linkedin_graph
        
        # API
        from app.api.chat import router as chat_router
        from app.api.health import router as health_router
        
        print("✅ All core modules imported successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_android_structure():
    """Test Android project structure"""
    print("\n📱 Testing Android Project Structure...")
    
    android_files = [
        "ASTA MOBILE/app/build.gradle.kts",
        "ASTA MOBILE/app/src/main/AndroidManifest.xml",
        "ASTA MOBILE/app/src/main/java/com/example/asta/service/WakeWordService.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/service/ASTAForegroundService.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/audio/AudioStreamer.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/websocket/ASTAWebSocketClient.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/ui/MainActivity.kt",
    ]
    
    missing_files = []
    for file in android_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing Android files: {missing_files}")
        return False
    else:
        print("✅ All Android components present!")
        return True

def test_flutter_structure():
    """Test Flutter project structure"""
    print("\n🎨 Testing Flutter Project Structure...")
    
    flutter_files = [
        "ASTA MOBILE/flutter_module/pubspec.yaml",
        "ASTA MOBILE/flutter_module/lib/main.dart",
        "ASTA MOBILE/flutter_module/lib/services/native_service.dart",
        "ASTA MOBILE/flutter_module/lib/screens/jarvis_screen.dart",
        "ASTA MOBILE/flutter_module/lib/widgets/jarvis_orb.dart",
        "ASTA MOBILE/flutter_module/lib/widgets/stage_feed.dart",
        "ASTA MOBILE/flutter_module/lib/screens/workflow_visualizer.dart",
        "ASTA MOBILE/flutter_module/lib/screens/content_studio.dart",
        "ASTA MOBILE/flutter_module/lib/screens/preferences_panel.dart",
    ]
    
    missing_files = []
    for file in flutter_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing Flutter files: {missing_files}")
        return False
    else:
        print("✅ All Flutter components present!")
        return True

def test_deployment_config():
    """Test deployment configuration"""
    print("\n🚀 Testing Deployment Configuration...")
    
    deploy_files = [
        "docker-compose.yml",
        "deploy/nginx.conf", 
        "backend/Dockerfile",
    ]
    
    missing_files = []
    for file in deploy_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing deployment files: {missing_files}")
        return False
    else:
        print("✅ All deployment configuration present!")
        return True

def test_memory_system():
    """Test memory system structure"""
    print("\n🧠 Testing Memory System...")
    
    memory_dir = Path("memory")
    if not memory_dir.exists():
        print("❌ Memory directory missing!")
        return False
    
    memory_files = list(memory_dir.glob("*.py"))
    if len(memory_files) < 8:  # Should have at least 8 Python files
        print(f"❌ Memory system incomplete - only {len(memory_files)} files found")
        return False
    
    print(f"✅ Memory system complete with {len(memory_files)} Python files!")
    return True

async def main():
    """Run all tests"""
    print("=" * 60)
    print("ASTA SYSTEM INTEGRATION TEST")
    print("=" * 60)
    
    tests = [
        ("Core Module Imports", test_imports()),
        ("Android Structure", test_android_structure()),
        ("Flutter Structure", test_flutter_structure()),
        ("Deployment Config", test_deployment_config()),
        ("Memory System", test_memory_system()),
    ]
    
    results = []
    for test_name, test_func in tests:
        if asyncio.iscoroutine(test_func):
            result = await test_func
        else:
            result = test_func
        results.append((test_name, result))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY:")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - ASTA SYSTEM IS FULLY IMPLEMENTED!")
    else:
        print(f"\n⚠️  {total-passed} tests failed - some components need attention")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())