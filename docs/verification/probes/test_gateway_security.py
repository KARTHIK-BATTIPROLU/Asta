import hashlib
import hmac
import json
import time
import uuid

from fastapi.testclient import TestClient

from backend.app.services.action_executor import OpenClawTool
from backend.gateway.openclaw_gateway import HMAC_SECRET, app, init_db

client = TestClient(app)


def sign_payload(payload: dict) -> dict:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(HMAC_SECRET, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    payload["hmac"] = sig
    return payload


def test_gateway_security_metacharacters():
    # Test that shell metacharacters are rejected
    malicious_targets = [
        "8.8.8.8; rm -rf /",
        "google.com && echo hacked",
        "localhost | cat /etc/passwd",
        "$(whoami)",
        "`whoami`",
        "127.0.0.1 > /tmp/hack",
    ]

    for target in malicious_targets:
        is_valid, msg, argv = OpenClawTool.validate_args("ping", ["-c", "4"], target)
        assert not is_valid
        assert "Shell metacharacters" in msg or "Invalid" in msg


def test_gateway_security_disallowed_argv():
    # Only allowed flags pass validation -- disallowed argv is rejected
    is_valid, msg, argv = OpenClawTool.validate_args("ping", ["-c", "4"], "8.8.8.8")
    assert is_valid

    # -p is not allowed in ping schema
    is_valid, msg, argv = OpenClawTool.validate_args("ping", ["-p", "80"], "8.8.8.8")
    assert not is_valid
    assert "Disallowed flag" in msg


def test_gateway_hmac_tampered_rejected():
    """A request signed correctly, then tampered with after signing, must be rejected."""
    payload = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "exec",
        "argv": ["python", "--version"],
        "cwd": "~/asta-projects",
    })
    payload["argv"] = ["python", "--pwn-me"]  # tamper after the HMAC was computed

    resp = client.post("/execute", json=payload)
    assert resp.status_code == 401
    assert "Invalid HMAC" in resp.json()["detail"]


def test_gateway_nonce_replay_rejected():
    """The same (ts, nonce) pair must not be usable twice."""
    init_db()

    nonce = str(uuid.uuid4())
    payload = sign_payload({
        "ts": int(time.time()),
        "nonce": nonce,
        "cmd": "exec",
        "argv": ["python", "--version"],
        "cwd": "~/asta-projects",
    })
    first = client.post("/execute", json=payload)
    assert first.status_code in [200, 500]  # allowed through auth/replay/jail checks

    replay = sign_payload({
        "ts": int(time.time()),
        "nonce": nonce,
        "cmd": "exec",
    })
    second = client.post("/execute", json=replay)
    assert second.status_code == 400
    assert "Invalid or reused nonce" in second.json()["detail"]


def test_gateway_path_outside_jail_rejected():
    """A cwd outside the sandbox jail must be rejected, whether given directly or via traversal."""
    payload_outside = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "exec",
        "argv": ["python", "--version"],
        "cwd": "/etc",
    })
    resp1 = client.post("/execute", json=payload_outside)
    assert resp1.status_code == 403
    assert "CWD outside jail" in resp1.json()["detail"]

    payload_traversal = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "exec",
        "argv": ["python", "../../../etc/passwd"],
        "cwd": "~/asta-projects",
    })
    resp2 = client.post("/execute", json=payload_traversal)
    assert resp2.status_code == 403
    assert "escapes jail" in resp2.json()["detail"]


def test_gateway_kill_switch_halts_execution():
    """The kill-switch command must halt execution and report a killed status."""
    payload = sign_payload({
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "cmd": "kill_switch",
    })
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "killed"
