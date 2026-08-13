import pytest
import sys
from unittest.mock import patch, MagicMock

# Mock pandas
sys.modules["pandas"] = None

from backend.app.api.health import health_check

@pytest.mark.asyncio
async def test_basic_health_check():
    # We just call the function directly
    response = await health_check()
    assert response["status"] == "ok"
    assert "timestamp" in response
