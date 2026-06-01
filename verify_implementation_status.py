#!/usr/bin/env python3
"""
ASTA Implementation Status Verification Script
Checks completion status of both ASTA_COMPLETE_IMPLEMENTATION.md and ASTA_VIBECODE_PLAN.md
"""

import os
import sys
from pathlib import Path

def check_file_exists(filepath):
    """Check if a file exists and return its status"""
    path = Path(filepath)
    if path.exists():
        size = path.stat().st_size
        return f"✅ EXISTS ({size} bytes)"
    else:
        return "❌ MISSING"

def check_directory_exists(dirpath):
    """Check if a directory exists and count files"""
    path = Path(dirpath)
    if path.exists() and path.is_dir():
        files = list(path.rglob("*"))
        file_count = len([f for f in files if f.is_file()])
        return f"✅ EXISTS ({file_count} files)"
    else:
        return "❌ MISSING"

def main():
    print("=" * 80)
    print("ASTA IMPLEMENTATION STATUS VERIFICATION")
    print("=" * 80)
    
    # Check implementation plan files
    print("\n📋 IMPLEMENTATION PLAN FILES:")
    print(f"ASTA_COMPLETE_IMPLEMENTATION.md: {check_file_exists('ASTA_COMPLETE_IMPLEMENTATION.md')}")
    print(f"ASTA_VIBECODE_PLAN.md: {check_file_exists('ASTA_VIBECODE_PLAN.md')}")
    
    # Backend Core Components (from COMPLETE_IMPLEMENTATION)
    print("\n🔧 BACKEND CORE COMPONENTS:")
    backend_files = [
        "backend/app/auth/middleware.py",
        "backend/app/core/state.py", 
        "backend/app/core/llm_router.py",
        "backend/app/core/supervisor.py",
        "backend/app/core/memory_engine.py",
        "backend/app/services/session_manager.py",
        "backend/app/services/llm_service.py",
        "backend/app/services/notion_service.py",
        "backend/app/services/research_service.py",
        "backend/app/services/weather_service.py",
        "backend/app/services/sheets_service.py",
        "backend/app/services/image_service.py",
        "backend/app/services/scheduler_service.py",
        "backend/app/services/preferences_service.py",
    ]
    
    for file in backend_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # Workflow Graphs
    print("\n🔄 WORKFLOW GRAPHS:")
    workflow_files = [
        "backend/app/workflows/routine_graph.py",
        "backend/app/workflows/research_graph.py", 
        "backend/app/workflows/linkedin_graph.py",
        "backend/app/workflows/youtube_graph.py",
        "backend/app/workflows/instagram_graph.py",
        "backend/app/workflows/habit_graph.py",
    ]
    
    for file in workflow_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # API Routes
    print("\n🌐 API ROUTES:")
    api_files = [
        "backend/app/api/routes.py",
        "backend/app/api/chat.py",
        "backend/app/api/preferences.py",
        "backend/app/api/content.py", 
        "backend/app/api/health.py",
    ]
    
    for file in api_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # Preference Files
    print("\n⚙️ PREFERENCE FILES:")
    pref_files = [
        "backend/preferences/linkedin_prefs.json",
        "backend/preferences/youtube_prefs.json",
        "backend/preferences/instagram_prefs.json",
        "backend/preferences/news_prefs.json",
    ]
    
    for file in pref_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # Android Components (from VIBECODE_PLAN)
    print("\n📱 ANDROID COMPONENTS:")
    android_files = [
        "ASTA MOBILE/app/build.gradle.kts",
        "ASTA MOBILE/app/src/main/AndroidManifest.xml",
        "ASTA MOBILE/app/src/main/java/com/example/asta/service/WakeWordService.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/service/ASTAForegroundService.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/audio/AudioStreamer.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/websocket/ASTAWebSocketClient.kt",
        "ASTA MOBILE/app/src/main/java/com/example/asta/ui/MainActivity.kt",
    ]
    
    for file in android_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # Flutter Components
    print("\n🎨 FLUTTER COMPONENTS:")
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
    
    for file in flutter_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # Production Deployment
    print("\n🚀 PRODUCTION DEPLOYMENT:")
    deploy_files = [
        "docker-compose.yml",
        "deploy/nginx.conf",
        "backend/Dockerfile",
    ]
    
    for file in deploy_files:
        print(f"{file}: {check_file_exists(file)}")
    
    # Memory System
    print("\n🧠 MEMORY SYSTEM:")
    print(f"memory/ directory: {check_directory_exists('memory')}")
    
    # Calculate completion percentage
    all_files = backend_files + workflow_files + api_files + pref_files + android_files + flutter_files + deploy_files
    existing_files = sum(1 for f in all_files if Path(f).exists())
    total_files = len(all_files)
    completion_pct = (existing_files / total_files) * 100
    
    print(f"\n📊 OVERALL COMPLETION STATUS:")
    print(f"Files implemented: {existing_files}/{total_files} ({completion_pct:.1f}%)")
    
    if completion_pct >= 95:
        print("🎉 IMPLEMENTATION IS COMPLETE!")
    elif completion_pct >= 80:
        print("⚠️  IMPLEMENTATION IS MOSTLY COMPLETE - few files missing")
    else:
        print("🔧 IMPLEMENTATION IN PROGRESS - significant work remaining")
    
    print("=" * 80)

if __name__ == "__main__":
    main()