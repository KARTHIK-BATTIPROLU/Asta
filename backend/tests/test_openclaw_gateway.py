import pytest
import time
import json
import uuid
import hmac
import hashlib
from fastapi.testclient import TestClient

from backend.gateway.openclaw_gateway import app, HMAC_SECRET, init_db, check_nonce

client = TestClient(app)

def sign_payload(payload: dict) -> dict:
    canonical = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    sig = hmac.new(HMAC_SECRET, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    payload["hmac"] = sig
    return payload

def test_missing_hmac():
    payload = {"v": 2, "cmd": "exec"}
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 401
    assert "Missing HMAC" in resp.json()["detail"]

def test_invalid_hmac():
    payload = {"v": 2, "cmd": "exec", "hmac": "bad"}
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 401
    assert "Invalid HMAC" in resp.json()["detail"]

def test_replay_protection():
    init_db()
    
    # 1. Old timestamp
    payload = sign_payload({
        "ts": int(time.time()) - 200,
        "nonce": str(uuid.uuid4()),
        "cmd": "exec"
    })
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 400
    assert "Timestamp out of window" in resp.json()["detail"]
    
    # 2. Valid
    valid_nonce = str(uuid.uuid4())
    payload2 = sign_payload({
        "ts": int(time.time()),
        "nonce": valid_nonce,
        "cmd": "exec",
        "argv": ["python", "--version"],
        "cwd": "~/asta-projects"
    })
    resp2 = client.post("/execute", json=payload2)
    # Could be 200 (if python exists) or 500 (if execution fails), but NOT 400/401/403
    assert resp2.status_code in [200, 500] 
    
    # 3. Replay with same nonce
    payload3 = sign_payload({
        "ts": int(time.time()),
        "nonce": valid_nonce,
        "cmd": "exec"
    })
    resp3 = client.post("/execute", json=payload3)
    assert resp3.status_code == 400
    assert "Invalid or reused nonce" in resp3.json()["detail"]

def test_allowlist():
    payload = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "exec",
        "argv": ["rm", "-rf", "/"],
        "cwd": "~/asta-projects"
    })
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 403
    assert "not in allowlist" in resp.json()["detail"]

def test_path_jail():
    # Outside jail CWD
    payload1 = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "exec",
        "argv": ["python", "--version"],
        "cwd": "/etc"
    })
    resp1 = client.post("/execute", json=payload1)
    assert resp1.status_code == 403
    assert "CWD outside jail" in resp1.json()["detail"]
    
    # Escape jail via args
    payload2 = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "exec",
        "argv": ["python", "../../../etc/passwd"],
        "cwd": "~/asta-projects"
    })
    resp2 = client.post("/execute", json=payload2)
    assert resp2.status_code == 403
    assert "escapes jail" in resp2.json()["detail"]

def test_kill_switch():
    payload = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "kill_switch"
    })
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "killed"
