import os
import sys
import time
import json
import uuid
import hmac
import hashlib
import sqlite3
import subprocess
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Gateway")

app = FastAPI(title="OpenClaw Gateway v2")

# Setup Jail and Secret
JAIL_DIR = os.path.expanduser("~/asta-projects")
os.makedirs(JAIL_DIR, exist_ok=True)
JAIL_PATH = Path(JAIL_DIR).resolve()

HMAC_SECRET = os.getenv("GATEWAY_HMAC_SECRET", "default_dev_secret").encode("utf-8")

# Setup SQLite Nonce Cache
DB_PATH = Path(os.path.expanduser("~/.asta/gateway.db"))
os.makedirs(DB_PATH.parent, exist_ok=True)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, ts INTEGER)"
        )
init_db()

ALLOWLIST = {
    "git", "python", "python3", "node", "npm", "npx",
    "pip", "uv", "ollama", "docker", "openclaw"
}

def clean_expired_nonces():
    cutoff = int(time.time()) - 86400  # 24h TTL
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM nonces WHERE ts < ?", (cutoff,))

def check_nonce(nonce: str, ts: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute("INSERT INTO nonces (nonce, ts) VALUES (?, ?)", (nonce, ts))
            return True
        except sqlite3.IntegrityError:
            return False

def verify_hmac(payload_str: str, provided_hmac: str) -> bool:
    expected_hmac = hmac.new(HMAC_SECRET, payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hmac, provided_hmac)

def is_safe_path(p: str, cwd: Path) -> bool:
    # If absolute, must be in jail. If relative, must resolve to in jail.
    try:
        if os.path.isabs(p):
            resolved = Path(p).resolve()
        else:
            resolved = (cwd / p).resolve()
            
        # Reject .. tricks resulting in paths outside jail
        # relative_to throws ValueError if not relative to jail
        resolved.relative_to(JAIL_PATH)
        return True
    except (ValueError, RuntimeError):
        return False

def log_audit(entry: dict):
    audit_file = DB_PATH.parent / "audit.jsonl"
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

@app.post("/execute")
async def execute_command(request: Request):
    try:
        raw_body = await request.body()
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 1. HMAC Verification
    provided_hmac = payload.pop("hmac", None)
    if not provided_hmac:
        raise HTTPException(status_code=401, detail="Missing HMAC")
        
    canonical_payload = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    if not verify_hmac(canonical_payload, provided_hmac):
        raise HTTPException(status_code=401, detail="Invalid HMAC")

    # 2. Replay Proof (120s window + Nonce)
    ts = payload.get("ts", 0)
    now = int(time.time())
    if abs(now - ts) > 120:
        raise HTTPException(status_code=400, detail="Timestamp out of window")
        
    nonce = payload.get("nonce", "")
    if not nonce or not check_nonce(nonce, ts):
        raise HTTPException(status_code=400, detail="Invalid or reused nonce")

    # Clean old nonces asynchronously occasionally
    if now % 10 == 0:
        clean_expired_nonces()

    cmd = payload.get("cmd", "")
    if cmd == "kill_switch":
        # In a real app this would kill process groups and lock
        logger.warning("KILL SWITCH ACTIVATED")
        return {"status": "killed"}

    if cmd != "exec":
        raise HTTPException(status_code=400, detail="Unknown cmd")

    argv = payload.get("argv", [])
    if not argv or not isinstance(argv, list):
        raise HTTPException(status_code=400, detail="Invalid argv")

    # 3. Command Allowlist
    base_cmd = argv[0]
    if base_cmd not in ALLOWLIST:
        raise HTTPException(status_code=403, detail=f"Command '{base_cmd}' not in allowlist")

    if base_cmd == "docker":
        if len(argv) < 2 or argv[1] not in ["compose"]:
            raise HTTPException(status_code=403, detail="Docker allowed for compose only")

    # 4. Path Jail
    cwd_raw = payload.get("cwd", str(JAIL_PATH))
    # Replace ~ with home dir safely
    if cwd_raw.startswith("~/"):
        cwd_raw = cwd_raw.replace("~", str(Path.home()), 1)
        
    cwd = Path(cwd_raw).resolve()
    
    try:
        cwd.relative_to(JAIL_PATH)
    except ValueError:
        raise HTTPException(status_code=403, detail="CWD outside jail")

    for arg in argv[1:]:
        # Heuristically check if arg is a path (contains / or \)
        if "/" in arg or "\\" in arg:
            # We don't block flags like --path=/foo, but we should be careful
            # For simplicity in this implementation, if it looks like a path, ensure it resolves in jail
            # If it's a flag, split by =
            check_val = arg.split("=", 1)[1] if "=" in arg else arg
            if ("/" in check_val or "\\" in check_val) and not check_val.startswith("-"):
                if not is_safe_path(check_val, cwd):
                    raise HTTPException(status_code=403, detail=f"Arg '{arg}' escapes jail")

    # 5. Env Scrubbing
    env = {
        "PATH": os.getenv("PATH", ""),
        "HOME": os.getenv("HOME", os.getenv("USERPROFILE", ""))
    }

    # 6. Execute (shell=False)
    timeout_s = payload.get("timeout_s", 60)
    
    start_time = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            exit_code = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            exit_code = -1
            stderr += b"\nTimeout exceeded"
            
        duration = time.time() - start_time
        
        log_audit({
            "id": payload.get("id", str(uuid.uuid4())),
            "ts": now,
            "argv": argv,
            "cwd": str(cwd),
            "exit": exit_code,
            "duration": duration,
            "bytes_out": len(stdout) + len(stderr)
        })

        return {
            "exit_code": exit_code,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace")
        }

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
