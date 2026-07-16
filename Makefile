.PHONY: verify

# Real verification, in order, failing loudly on any step:
#   (a) import backend.app.main from a clean cwd
#   (b) boot check: start uvicorn, poll /api/health/ until 200 (30s timeout), kill it
#   (c) pytest across docs/verification/probes, backend/tests, tests
#   (d) nonzero exit on ANY failure (see scripts/verify.sh)
verify:
	@bash scripts/verify.sh
