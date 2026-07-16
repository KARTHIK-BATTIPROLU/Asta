import pytest
from backend.app.services.action_executor import OpenClawTool

def test_gateway_security_metacharacters():
    # Test that shell metacharacters are rejected
    malicious_targets = [
        "8.8.8.8; rm -rf /",
        "google.com && echo hacked",
        "localhost | cat /etc/passwd",
        "$(whoami)",
        "`whoami`",
        "127.0.0.1 > /tmp/hack"
    ]
    
    for target in malicious_targets:
        is_valid, msg, argv = OpenClawTool.validate_args("ping", ["-c", "4"], target)
        assert not is_valid
        assert "Shell metacharacters" in msg or "Invalid" in msg

def test_gateway_security_allowed_flags():
    # Test that only allowed flags pass validation
    is_valid, msg, argv = OpenClawTool.validate_args("ping", ["-c", "4"], "8.8.8.8")
    assert is_valid
    
    # -p is not allowed in ping schema
    is_valid, msg, argv = OpenClawTool.validate_args("ping", ["-p", "80"], "8.8.8.8")
    assert not is_valid
    assert "Disallowed flag" in msg
