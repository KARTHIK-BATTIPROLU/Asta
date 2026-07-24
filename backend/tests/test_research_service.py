import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Mock heavy/networked dependencies for the duration of this import only, then
# restore sys.modules so other test files in the same pytest run get the real
# modules back (leaving these mocked leaks a poisoned llm_factory into every
# test that imports it afterward, e.g. tests/test_router.py).
import sys
_MOCKED_MODULES = [
    "backend.app.api.ws_transport",
    "backend.app.core.llm_factory",
]
_original_modules = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
for _name in _MOCKED_MODULES:
    sys.modules[_name] = MagicMock()

from backend.app.services.research_service import research_service

for _name, _mod in _original_modules.items():
    if _mod is not None:
        sys.modules[_name] = _mod
    else:
        sys.modules.pop(_name, None)

@pytest.fixture
def mock_router():
    with patch("backend.app.services.research_service.router") as mock:
        yield mock

@pytest.fixture
def mock_graph_ltm():
    with patch("backend.app.services.research_service.graph_ltm") as mock:
        yield mock

@pytest.fixture
def mock_deep_research():
    with patch.object(research_service, "deep_research") as mock:
        yield mock

@pytest.fixture
def mock_broadcast():
    with patch("backend.app.services.research_service.broadcast_message") as mock:
        yield mock

@pytest.mark.asyncio
async def test_run_research(mock_router, mock_graph_ltm, mock_deep_research, mock_broadcast):
    # Mock deep research fetching
    mock_deep_research.return_value = {
        "sources": [
            {"title": "Doc 1", "url": "http://test.com", "content": "Content"}
        ]
    }

    # Mock LLM for map-reduce
    mock_llm_res = MagicMock()
    mock_llm_res.text = "Synthesized claims."
    mock_router.run = AsyncMock(return_value=mock_llm_res)

    # Mock memory
    mock_graph_ltm.add_episode = AsyncMock()

    session_id = "test_session_1"
    recap = await research_service.run_research(session_id, "test topic", "test idea")

    # Verify Recap
    assert recap == "Synthesized claims."

    # Verify memory stored
    mock_graph_ltm.add_episode.assert_called_once()
    args, kwargs = mock_graph_ltm.add_episode.call_args
    assert args[0] == session_id
    assert "test topic" in args[1]
    
    # Verify Active Session
    assert session_id in research_service.active_sessions
    doc = research_service.active_sessions[session_id]["doc"]
    assert "# test topic" in doc
    assert "## HIS IDEA" in doc
    assert "## FINDINGS" in doc
    
@pytest.mark.asyncio
async def test_run_followup():
    session_id = "test_session_2"
    research_service.active_sessions[session_id] = {
        "topic": "test",
        "doc": "Initial Doc.",
        "sources": []
    }
    
    # Test Deeper
    res = await research_service.run_followup(session_id, "go deeper into testing")
    assert "expanded the document" in res
    assert "### Deeper: go deeper into testing" in research_service.active_sessions[session_id]["doc"]
    
    # Test Project Mode
    res2 = await research_service.run_followup(session_id, "build a project")
    assert "Architecture appended" in res2
    assert "## ARCHITECTURE" in research_service.active_sessions[session_id]["doc"]
