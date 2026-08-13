import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from backend.app.voice.wakeword_processor import ServerWakeWordConfirmProcessor
from pipecat.frames.frames import AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection


def _make_processor(**kwargs):
    with patch("backend.app.voice.wakeword_processor.openwakeword.utils.download_models"), \
         patch("backend.app.voice.wakeword_processor.Model") as mock_model_cls:
        mock_model_cls.return_value = MagicMock()
        processor = ServerWakeWordConfirmProcessor(**kwargs)
        processor.oww_model = MagicMock()
        return processor


@pytest.mark.asyncio
async def test_wakeword_processor_drops_audio_until_trigger():
    processor = _make_processor(threshold=0.6, sample_rate=16000)
    processor.oww_model.predict = lambda x: {"hey_asta": 0.1}

    silence = b'\x00' * 3200
    frame = AudioRawFrame(audio=silence, sample_rate=16000, num_channels=1)

    frames_pushed = []
    async def mock_push_frame(f, d=FrameDirection.UPSTREAM):
        frames_pushed.append(f)
    processor.push_frame = mock_push_frame

    await processor.process_frame(frame, FrameDirection.UPSTREAM)

    assert processor.has_confirmed is False
    assert len(frames_pushed) == 0


@pytest.mark.asyncio
async def test_wakeword_processor_passes_downstream_on_trigger():
    processor = _make_processor(threshold=0.6, sample_rate=16000)
    processor.oww_model.predict = lambda x: {"hey_asta": 0.9}

    audio_data = b'\x01' * 3200
    frame = AudioRawFrame(audio=audio_data, sample_rate=16000, num_channels=1)

    frames_pushed = []
    async def mock_push_frame(f, d=FrameDirection.UPSTREAM):
        frames_pushed.append(f)
    processor.push_frame = mock_push_frame

    await processor.process_frame(frame, FrameDirection.UPSTREAM)

    assert processor.has_confirmed is True
    assert len(frames_pushed) == 1
    assert isinstance(frames_pushed[0], AudioRawFrame)
