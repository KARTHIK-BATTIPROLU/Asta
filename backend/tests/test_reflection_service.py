import pytest
import asyncio
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Mock ws_transport so we don't load pipecat and its dependencies
sys.modules["backend.app.api.ws_transport"] = MagicMock()

from backend.app.services.reflection_service import reflection_service

@pytest.fixture
def mock_router():
    with patch("backend.app.services.reflection_service.router") as mock_router:
        yield mock_router

@pytest.fixture
def mock_reminder_service():
    with patch("backend.app.services.reflection_service.reminder_service") as mock_rem:
        yield mock_rem

@pytest.mark.asyncio
async def test_run_daily_recap(mock_router, mock_reminder_service):
    # Mock LLM response
    mock_llm_res = MagicMock()
    mock_llm_res.text = "This is a mock daily recap."
    mock_router.run = AsyncMock(return_value=mock_llm_res)
    mock_reminder_service.schedule_reminder = AsyncMock()
    
    await reflection_service.run_daily_recap()
    
    mock_router.run.assert_called_once()
    args, _ = mock_router.run.call_args
    assert "realtime_chat" == args[0]
    
    # Assert reminder scheduled
    mock_reminder_service.schedule_reminder.assert_called_once()
    rem_args, rem_kwargs = mock_reminder_service.schedule_reminder.call_args
    assert rem_kwargs["text"] == "This is a mock daily recap."

@pytest.mark.asyncio
async def test_run_sunday_reflection(mock_router, mock_reminder_service):
    # Mock LLM response
    mock_llm_res = MagicMock()
    mock_llm_res.text = "This is a long mock sunday reflection spanning more than 200 chars. " * 10
    mock_router.run = AsyncMock(return_value=mock_llm_res)
    mock_reminder_service.schedule_reminder = AsyncMock()
    
    await reflection_service.run_sunday_reflection()
    
    mock_router.run.assert_called_once()
    
    # Assert reminder scheduled with truncated text
    mock_reminder_service.schedule_reminder.assert_called_once()
    rem_args, rem_kwargs = mock_reminder_service.schedule_reminder.call_args
    assert len(rem_kwargs["text"]) == 200
