import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from pipecat.frames.frames import TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection

from backend.app.voice.memory_injector import MemoryContextInjector, SystemPromptUpdateFrame

@pytest.mark.asyncio
async def test_memory_voice_integration():
    # Setup the injector
    injector = MemoryContextInjector()
    
    # Mock push_frame to capture what the injector outputs
    injector.push_frame = AsyncMock()
    
    # The frame simulating user speech
    user_frame = TranscriptionFrame(text="Where did I put my keys?", user_id="karthik", timestamp="now")
    
    # Mock recall to return a relevant memory
    with patch("backend.app.voice.memory_injector.recall", new_callable=AsyncMock) as mock_recall:
        mock_recall.return_value = [{"text": "Karthik left his keys on the kitchen counter."}]
        
        # Process the frame UPSTREAM
        await injector.process_frame(user_frame, FrameDirection.UPSTREAM)
        
        # Verify recall was called with the transcription text
        mock_recall.assert_called_once_with("Where did I put my keys?", k=6)
        
        # Verify push_frame was called twice: once for the context update, once for the original frame
        assert injector.push_frame.call_count == 2
        
        call_1_args = injector.push_frame.call_args_list[0][0]
        call_2_args = injector.push_frame.call_args_list[1][0]
        
        # First push should be SystemPromptUpdateFrame
        assert isinstance(call_1_args[0], SystemPromptUpdateFrame)
        assert "Karthik left his keys on the kitchen counter." in call_1_args[0].system_prompt
        assert call_1_args[1] == FrameDirection.UPSTREAM
        
        # Second push should be the original TranscriptionFrame
        assert call_2_args[0] is user_frame
        assert call_2_args[1] == FrameDirection.UPSTREAM
