import pytest
from unittest.mock import AsyncMock, patch

from pipecat.frames.frames import TranscriptionFrame, VADUserStartedSpeakingFrame
from pipecat.processors.frame_processor import FrameDirection

from backend.app.voice.pipeline import LanguageSplitTTS, RouterLLMService, VadOrbNotifier


@pytest.mark.asyncio
async def test_vad_orb_notifier_emits_listening_and_forwards_frame():
    notifier = VadOrbNotifier()
    notifier.push_frame = AsyncMock()

    frame = VADUserStartedSpeakingFrame()
    with patch("backend.app.voice.pipeline._emit_orb_state", new_callable=AsyncMock) as mock_emit:
        await notifier.process_frame(frame, FrameDirection.DOWNSTREAM)

    mock_emit.assert_awaited_once_with("listening")
    notifier.push_frame.assert_awaited_once_with(frame, FrameDirection.DOWNSTREAM)


@pytest.mark.asyncio
async def test_router_llm_service_emits_thinking_on_transcription():
    service = RouterLLMService(task="realtime_chat")
    service.push_frame = AsyncMock()

    frame = TranscriptionFrame(text="hello", user_id="karthik", timestamp="now")
    with patch("backend.app.voice.pipeline._emit_orb_state", new_callable=AsyncMock) as mock_emit, \
         patch("backend.app.voice.pipeline.router") as mock_router:
        mock_router.run = AsyncMock(side_effect=Exception("no real LLM call in this test"))
        await service.process_frame(frame, FrameDirection.DOWNSTREAM)

    mock_emit.assert_any_call("thinking")


@pytest.mark.asyncio
async def test_language_split_tts_emits_speaking_then_idle():
    tts = LanguageSplitTTS()

    async def fake_run_tts(text, context_id=""):
        yield "frame-1"
        yield "frame-2"

    tts.fallback = type("FakeFallback", (), {"run_tts": staticmethod(fake_run_tts)})()

    emitted = []
    with patch("backend.app.voice.pipeline._emit_orb_state", new_callable=AsyncMock) as mock_emit:
        mock_emit.side_effect = lambda state: emitted.append(state)
        frames = [f async for f in tts.run_tts("hello there")]

    assert frames == ["frame-1", "frame-2"]
    assert emitted == ["speaking", "idle"]
