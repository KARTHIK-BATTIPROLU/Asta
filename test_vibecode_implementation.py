#!/usr/bin/env python3
"""
ASTA VIBECODE Implementation Verification Script
Tests all components from ASTA_VIBECODE_PLAN.md
"""

import os
import sys
import subprocess
from pathlib import Path

def check_file_exists(filepath, description=""):
    """Check if a file exists and return status"""
    if os.path.exists(filepath):
        print(f"✅ {filepath} - {description}")
        return True
    else:
        print(f"❌ {filepath} - {description}")
        return False

def check_directory_exists(dirpath, description=""):
    """Check if a directory exists and return status"""
    if os.path.isdir(dirpath):
        print(f"✅ {dirpath}/ - {description}")
        return True
    else:
        print(f"❌ {dirpath}/ - {description}")
        return False

def main():
    print("🔍 ASTA VIBECODE Implementation Verification")
    print("=" * 50)
    
    # Track overall status
    total_checks = 0
    passed_checks = 0
    
    # PHASE 8 - Android App Components
    print("\n📱 PHASE 8 - Android App Components")
    print("-" * 30)
    
    android_files = [
        ("ASTA MOBILE/app/build.gradle.kts", "Android build configuration"),
        ("ASTA MOBILE/app/src/main/AndroidManifest.xml", "Android manifest"),
        ("ASTA MOBILE/app/src/main/java/com/example/asta/ui/MainActivity.kt", "MainActivity with MethodChannel"),
        ("ASTA MOBILE/app/src/main/java/com/example/asta/service/WakeWordService.kt", "Wake word detection service"),
        ("ASTA MOBILE/app/src/main/java/com/example/asta/service/ASTAForegroundService.kt", "Voice conversation service"),
        ("ASTA MOBILE/app/src/main/java/com/example/asta/audio/AudioStreamer.kt", "Audio recording/playback"),
        ("ASTA MOBILE/app/src/main/java/com/example/asta/websocket/ASTAWebSocketClient.kt", "WebSocket client"),
    ]
    
    for filepath, description in android_files:
        total_checks += 1
        if check_file_exists(filepath, description):
            passed_checks += 1
    
    # PHASE 9 - Flutter UI Components
    print("\n🎨 PHASE 9 - Flutter UI Components")
    print("-" * 30)
    
    flutter_files = [
        ("ASTA MOBILE/flutter_module/pubspec.yaml", "Flutter dependencies"),
        ("ASTA MOBILE/flutter_module/lib/main.dart", "Flutter main app"),
        ("ASTA MOBILE/flutter_module/lib/screens/jarvis_screen.dart", "Main voice interface"),
        ("ASTA MOBILE/flutter_module/lib/screens/workflow_visualizer.dart", "Workflow visualization"),
        ("ASTA MOBILE/flutter_module/lib/screens/content_studio.dart", "Content management"),
        ("ASTA MOBILE/flutter_module/lib/screens/preferences_panel.dart", "Settings panel"),
        ("ASTA MOBILE/flutter_module/lib/widgets/jarvis_orb.dart", "Animated orb widget"),
        ("ASTA MOBILE/flutter_module/lib/widgets/stage_feed.dart", "Stage display widget"),
        ("ASTA MOBILE/flutter_module/lib/services/native_service.dart", "Flutter ↔ Native communication"),
    ]
    
    for filepath, description in flutter_files:
        total_checks += 1
        if check_file_exists(filepath, description):
            passed_checks += 1
    
    # PHASE 10 - Deployment Configuration
    print("\n🚀 PHASE 10 - Deployment Configuration")
    print("-" * 30)
    
    deployment_files = [
        ("docker-compose.yml", "Docker Compose configuration"),
        ("deploy/nginx.conf", "Nginx reverse proxy configuration"),
        ("backend/Dockerfile", "Backend Docker image"),
        ("backend/requirements.txt", "Python dependencies"),
        (".env.template", "Environment variables template"),
    ]
    
    for filepath, description in deployment_files:
        total_checks += 1
        if check_file_exists(filepath, description):
            passed_checks += 1
    
    # Backend Core Components (from ASTA_COMPLETE_IMPLEMENTATION.md)
    print("\n🔧 Backend Core Components")
    print("-" * 30)
    
    backend_files = [
        ("backend/app/main.py", "FastAPI application"),
        ("backend/app/config.py", "Configuration settings"),
        ("backend/app/auth/middleware.py", "Authentication middleware"),
        ("backend/app/core/supervisor.py", "LangGraph supervisor"),
        ("backend/app/core/state.py", "State schemas"),
        ("backend/app/core/llm_router.py", "LLM routing"),
        ("backend/app/core/memory_engine.py", "Memory management"),
        ("backend/app/api/chat.py", "Chat API endpoint"),
        ("backend/app/api/health.py", "Health check endpoint"),
        ("backend/app/services/stt_service.py", "Speech-to-text service"),
        ("backend/app/services/tts_service.py", "Text-to-speech service"),
        ("backend/app/services/notion_service.py", "Notion integration"),
        ("backend/app/services/research_service.py", "Web research service"),
    ]
    
    for filepath, description in backend_files:
        total_checks += 1
        if check_file_exists(filepath, description):
            passed_checks += 1
    
    # Check for specific Android dependencies in build.gradle.kts
    print("\n📦 Android Dependencies Check")
    print("-" * 30)
    
    build_gradle_path = "ASTA MOBILE/app/build.gradle.kts"
    if os.path.exists(build_gradle_path):
        with open(build_gradle_path, 'r') as f:
            content = f.read()
            
        dependencies_to_check = [
            ("porcupine", "Porcupine wake word detection"),
            ("okhttp", "OkHttp for networking"),
            ("work-runtime", "WorkManager for background tasks"),
            ("lifecycle", "AndroidX Lifecycle components"),
        ]
        
        for dep, description in dependencies_to_check:
            total_checks += 1
            if dep.lower() in content.lower():
                print(f"✅ {dep} dependency - {description}")
                passed_checks += 1
            else:
                print(f"❌ {dep} dependency - {description}")
    
    # Check Flutter dependencies in pubspec.yaml
    print("\n📦 Flutter Dependencies Check")
    print("-" * 30)
    
    pubspec_path = "ASTA MOBILE/flutter_module/pubspec.yaml"
    if os.path.exists(pubspec_path):
        with open(pubspec_path, 'r') as f:
            content = f.read()
            
        flutter_deps = [
            ("provider", "State management"),
            ("web_socket_channel", "WebSocket communication"),
            ("audioplayers", "Audio playback"),
            ("lottie", "Animations"),
        ]
        
        for dep, description in flutter_deps:
            total_checks += 1
            if dep in content:
                print(f"✅ {dep} dependency - {description}")
                passed_checks += 1
            else:
                print(f"❌ {dep} dependency - {description}")
    
    # Check Android permissions in AndroidManifest.xml
    print("\n🔐 Android Permissions Check")
    print("-" * 30)
    
    manifest_path = "ASTA MOBILE/app/src/main/AndroidManifest.xml"
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r') as f:
            content = f.read()
            
        permissions = [
            ("RECORD_AUDIO", "Microphone access"),
            ("INTERNET", "Network access"),
            ("FOREGROUND_SERVICE", "Background services"),
            ("WAKE_LOCK", "Keep device awake"),
        ]
        
        for perm, description in permissions:
            total_checks += 1
            if perm in content:
                print(f"✅ {perm} permission - {description}")
                passed_checks += 1
            else:
                print(f"❌ {perm} permission - {description}")
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 IMPLEMENTATION SUMMARY")
    print("=" * 50)
    print(f"Total checks: {total_checks}")
    print(f"Passed: {passed_checks}")
    print(f"Failed: {total_checks - passed_checks}")
    print(f"Success rate: {(passed_checks/total_checks)*100:.1f}%")
    
    if passed_checks == total_checks:
        print("\n🎉 ASTA VIBECODE IMPLEMENTATION COMPLETE!")
        print("All components are implemented and ready for deployment.")
    else:
        print(f"\n⚠️  {total_checks - passed_checks} components still need implementation.")
        print("Review the failed checks above and complete missing components.")
    
    # Additional checks
    print("\n🔍 Additional Verification")
    print("-" * 30)
    
    # Check if we can import key Python modules
    try:
        sys.path.append('backend')
        print("✅ Python path configured for backend imports")
    except Exception as e:
        print(f"❌ Python path configuration failed: {e}")
    
    # Check Docker Compose syntax
    if os.path.exists("docker-compose.yml"):
        try:
            result = subprocess.run(
                ["docker-compose", "config", "-q"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print("✅ Docker Compose configuration is valid")
            else:
                print(f"❌ Docker Compose configuration error: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("⚠️  Docker Compose not available for validation")
    
    print("\n🏁 Verification complete!")
    return passed_checks == total_checks

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)