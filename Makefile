.PHONY: verify

verify:
	@echo "--- Phase 0 Verification ---"
	@echo "Checking import backend.app.main..."
	@python -c "import backend.app.main" && echo "[OK] import backend.app.main" || (echo "[FAIL] import backend.app.main" && exit 1)
	@echo "--- Phase 1 Verification ---"
	@echo "Checking import backend.app.voice.pipeline..."
	@python -c "import backend.app.voice.pipeline" && echo "[OK] import backend.app.voice.pipeline" || (echo "[FAIL] import backend.app.voice.pipeline" && exit 1)
	@echo "Running Pytest for Router..."
	@python -m pytest tests/test_router.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 2 Verification ---"
	@echo "Checking import backend.app.voice.wakeword_processor..."
	@python -c "import backend.app.voice.wakeword_processor" && echo "[OK] import wakeword_processor" || (echo "[FAIL] import wakeword_processor" && exit 1)
	@echo "Running Pytest for WakeWord Parity..."
	@python -m pytest backend/tests/test_wakeword_parity.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 3 Verification ---"
	@echo "Checking import backend.app.services.memory.extractor..."
	@python -c "import backend.app.services.memory.extractor" && echo "[OK] import extractor" || (echo "[FAIL] import extractor" && exit 1)
	@echo "Checking import backend.app.services.memory.graph_ltm..."
	@python -c "import backend.app.services.memory.graph_ltm" && echo "[OK] import graph_ltm" || (echo "[FAIL] import graph_ltm" && exit 1)
	@echo "Running Pytest for Recall Scoring..."
	@python -m pytest backend/tests/test_recall_scoring.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "Running Pytest for Memory Extraction..."
	@python -m pytest backend/tests/test_memory_extraction.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 4 Verification ---"
	@echo "Checking import backend.app.services.morning_service..."
	@python -c "import backend.app.services.morning_service" && echo "[OK] import morning_service" || (echo "[FAIL] import morning_service" && exit 1)
	@echo "Running Pytest for Weather Service..."
	@python -m pytest backend/tests/test_weather_service.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "Running Pytest for News Service..."
	@python -m pytest backend/tests/test_news_service.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 5 Verification ---"
	@echo "Running Pytest for Reminder Service..."
	@python -m pytest backend/tests/test_reminder_service.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 6 Verification ---"
	@echo "Running Pytest for Habit Service..."
	@python -m pytest backend/tests/test_habit_service.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "Running Pytest for Reflection Service..."
	@python -m pytest backend/tests/test_reflection_service.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 7 Verification ---"
	@echo "Running Pytest for Research Service..."
	@python -m pytest backend/tests/test_research_service.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 8 Verification ---"
	@echo "Running Pytest for OpenClaw Gateway..."
	@python -m pytest backend/tests/test_openclaw_gateway.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 9 Verification ---"
	@echo "Running Pytest for Sync Routes..."
	@python -m pytest backend/tests/test_sync_routes.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "--- Phase 10 Verification ---"
	@echo "Running Pytest for Health Routes..."
	@python -m pytest backend/tests/test_health_routes.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "All verify checks passed."
