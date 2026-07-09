.PHONY: verify

verify:
	@echo "--- Phase 0 Verification ---"
	@echo "Checking import backend.app.main..."
	@python -c "import backend.app.main" && echo "[OK] import backend.app.main" || (echo "[FAIL] import backend.app.main" && exit 1)
	@echo "All Phase 0 verify checks passed."
