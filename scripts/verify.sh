#!/usr/bin/env bash
# Real verification: import check -> boot check (uvicorn + /health poll) -> pytest.
# Exits nonzero and prints the failing step loudly on ANY failure. No unconditional
# success echo: the final line only runs if every prior step returned 0.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON=${PYTHON:-python}
PORT=${VERIFY_PORT:-8791}
LOGFILE="$(mktemp)"
UVICORN_PID=""

cleanup() {
  if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill "$UVICORN_PID" 2>/dev/null
    sleep 1
    if kill -0 "$UVICORN_PID" 2>/dev/null && command -v taskkill >/dev/null 2>&1; then
      taskkill //F //T //PID "$UVICORN_PID" >/dev/null 2>&1
    fi
  fi
  rm -f "$LOGFILE"
}
trap cleanup EXIT

fail() {
  echo "[FAIL] $1"
  exit 1
}

echo "--- (a) Import check: backend.app.main ---"
TMPDIR_IMPORT="$(mktemp -d)"
if ( cd "$TMPDIR_IMPORT" && PYTHONPATH="$REPO_ROOT" "$PYTHON" -c "import backend.app.main" ); then
  echo "[OK] import backend.app.main"
else
  fail "import backend.app.main raised (see traceback above)"
fi
rm -rf "$TMPDIR_IMPORT"

echo "--- (b) Boot check: uvicorn + /api/health/ poll ---"
"$PYTHON" -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" > "$LOGFILE" 2>&1 &
UVICORN_PID=$!

ok=0
code="000"
for i in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/health/" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    ok=1
    break
  fi
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [ "$ok" -ne 1 ]; then
  echo "----- server log ($LOGFILE) -----"
  cat "$LOGFILE"
  fail "boot check: /api/health/ never returned 200 within 30s (last code: $code)"
fi

if grep -qi "Traceback (most recent call last)" "$LOGFILE"; then
  echo "----- server log ($LOGFILE) -----"
  cat "$LOGFILE"
  fail "boot check: got 200 but a traceback appeared in the server log"
fi

echo "[OK] boot check: /api/health/ -> 200, no traceback in log"

if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
  kill "$UVICORN_PID" 2>/dev/null
  sleep 1
  if kill -0 "$UVICORN_PID" 2>/dev/null && command -v taskkill >/dev/null 2>&1; then
    taskkill //F //T //PID "$UVICORN_PID" >/dev/null 2>&1
  fi
fi
UVICORN_PID=""

echo "--- (c) Pytest: docs/verification/probes backend/tests tests ---"
if "$PYTHON" -m pytest docs/verification/probes backend/tests tests -q; then
  echo "[OK] pytest"
else
  fail "pytest reported failing tests"
fi

echo "All verify checks passed."
