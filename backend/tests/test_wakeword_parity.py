import pytest
import numpy as np
from backend.app.voice.wakeword_processor import ServerWakeWordConfirmProcessor
from pipecat.frames.frames import AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection
import asyncio

@pytest.mark.asyncio
async def test_wakeword_processor_rejects_silence():
    processor = ServerWakeWordConfirmProcessor(threshold=0.6, buffer_duration_sec=1.5, sample_rate=16000)
    
    # 1.5 seconds of silence (16kHz * 2 bytes = 32000 bytes per second -> 48000 bytes)
    silence = b'\x00' * 48000
    frame = AudioRawFrame(audio=silence, sample_rate=16000, num_channels=1)
    
    with pytest.raises(Exception, match="False Accept Wake Word - Terminating"):
        await processor.process_frame(frame, FrameDirection.UPSTREAM)

@pytest.mark.asyncio
async def test_wakeword_processor_passes_downstream_on_trigger():
    # If we could mock the openwakeword model here, we would test a positive trigger.
    # For now, we stub the model predict to always pass.
    processor = ServerWakeWordConfirmProcessor(threshold=0.6, buffer_duration_sec=0.1, sample_rate=16000)
    
    # Mock predict
    processor.oww_model.predict = lambda x: {"hey_jarvis": 0.9}
    
    audio_data = b'\x01' * 3200 # 0.1s
    frame = AudioRawFrame(audio=audio_data, sample_rate=16000, num_channels=1)
    
    # We need a mock downstream to catch the push_frame
    frames_pushed = []
    async def mock_push_frame(f, d=FrameDirection.DOWNSTREAM):
        frames_pushed.append(f)
        
    processor.push_frame = mock_push_frame
    
    await processor.process_frame(frame, FrameDirection.UPSTREAM)
    
    assert processor.has_confirmed is True
    assert len(frames_pushed) == 1
    assert isinstance(frames_pushed[0], AudioRawFrame)
