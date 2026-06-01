#!/usr/bin/env python3
"""Quick import test"""

print("Testing imports...")

tests = [
    "backend.app.auth.middleware",
    "backend.app.core.state",
    "backend.app.core.llm_router",
    "backend.app.services.l1_cache",
    "backend.app.services.notion_service",
    "backend.app.services.research_service",
    "backend.app.services.weather_service",
    "backend.app.services.sheets_service",
    "backend.app.services.scheduler_service",
    "backend.app.workflows.routine_graph",
    "backend.app.workflows.research_graph",
    "backend.app.workflows.linkedin_graph",
    "backend.app.core.supervisor",
]

passed = 0
failed = 0

for module in tests:
    try:
        __import__(module)
        print(f"[OK] {module}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {module}: {str(e)[:60]}")
        failed += 1

print(f"\nPassed: {passed}/{passed+failed}")
