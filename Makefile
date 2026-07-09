.PHONY: verify

verify:
	@echo "--- Phase 0 Verification ---"
	@echo "Checking import backend.app.main..."
	@python -c "import backend.app.main" && echo "[OK] import backend.app.main" || (echo "[FAIL] import backend.app.main" && exit 1)
	@echo "--- Phase 1 Verification ---"
	@echo "Checking import backend.app.voice.pipeline..."
	@python -c "import backend.app.voice.pipeline" && echo "[OK] import backend.app.voice.pipeline" || (echo "[FAIL] import backend.app.voice.pipeline" && exit 1)
	@echo "Running Pytest for Router..."
	@pytest tests/test_router.py -q && echo "[OK] Pytest passed" || (echo "[FAIL] Pytest failed" && exit 1)
	@echo "All verify checks passed."
