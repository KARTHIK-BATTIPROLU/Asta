import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from pipecat.frames.frames import TranscriptionFrame, TextFrame
from backend.app.voice.pipeline import build_pipeline
from backend.app.voice.reflex import ReflexProcessor

@pytest.mark.asyncio
async def test_step_1_and_2():
    # Step 1: Instantiate voice pipeline
    class DummyTransport:
        def input(self): return MagicMock()
        def output(self): return MagicMock()
        
    transport = DummyTransport()
    # Mocking edge_tts import for environment compatibility if it fails
    
    pipeline = build_pipeline(transport)
    assert pipeline is not None, "Pipeline failed to instantiate"
    
    # Extract ReflexProcessor
    reflex = None
    for proc in pipeline.processors:
        if isinstance(proc, ReflexProcessor):
            reflex = proc
            break
            
    assert reflex is not None, "ReflexProcessor missing from pipeline"
    
    # Step 2: transcription frame flows -> ReflexProcessor emits filler
    reflex.push_frame = AsyncMock()
    
    frame = TranscriptionFrame(text="uh can you research the latest quantum computing news for me?", user_id="user1", timestamp="123")
    await reflex.process_frame(frame, direction=None)
    
    # Ensure it emitted a filler
    # "research" triggers filler
    reflex.push_frame.assert_called()
    
    emitted_texts = []
    for call in reflex.push_frame.call_args_list:
        frame_arg = call[0][0]
        if hasattr(frame_arg, 'text'):
            emitted_texts.append(frame_arg.text)
            
    # Check if any filler is in the emitted texts
    expected_fillers = [
        "Let me dig that up for you.", "Searching my memory banks.", "Hold on, looking through the archives.",
        "I'll look into that right away.", "Scanning the web for you.", "Give me a second to research that.",
        "Hmm, let me think.", "Interesting. Just a moment.", "Processing that now.",
        "Got it. One second.", "On it.", "Sure thing, boss."
    ]
    assert any(filler in emitted_texts for filler in expected_fillers), f"No filler emitted. Emitted: {emitted_texts}"
