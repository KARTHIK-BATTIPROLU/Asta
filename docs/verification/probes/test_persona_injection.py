import uuid

import pytest
from unittest.mock import AsyncMock

from pipecat.frames.frames import TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection

from backend.app.db.database import db_manager
from backend.app.db.memory_handler import memory_handler
from backend.app.services.memory.extractor import _generate_embedding
from backend.app.voice.memory_injector import MemoryContextInjector, SystemPromptUpdateFrame


@pytest.mark.asyncio
async def test_persona_injection_real_wire():
    """
    (a) test_persona_injection.py: extend the REAL wire path — seed a fact, run the unpatched
    injector, assert BOTH a persona marker line AND the recalled fact are present in the final
    assembled prompt, in the right order. No mocks on the memory path.
    """
    await db_manager.connect()
    if db_manager.db is None:
        pytest.skip("MONGO_URI not configured -- cannot run the real memory wire test")

    session_id = f"wire-test-{uuid.uuid4().hex[:8]}"
    fact_text = f"Karthik loves biryani (wire-test {uuid.uuid4().hex[:6]})."
    embedding = await _generate_embedding(fact_text)

    stored = await memory_handler.store_insight(
        session_id=session_id,
        kind="fact",
        text=fact_text,
        entities=["biryani"],
        confidence=0.95,
        embedding=embedding,
        pinned=False,
    )
    assert stored, "setup: failed to write the seed fact via the real store_insight path"

    try:
        injector = MemoryContextInjector()
        injector.push_frame = AsyncMock()

        user_frame = TranscriptionFrame(text="Do I love biryani?", user_id="karthik", timestamp="now")
        await injector.process_frame(user_frame, FrameDirection.DOWNSTREAM)

        injector.push_frame.assert_called()

        call_1_args = injector.push_frame.call_args_list[0][0]
        call_2_args = injector.push_frame.call_args_list[1][0]

        assert isinstance(call_1_args[0], SystemPromptUpdateFrame)
        system_prompt = call_1_args[0].system_prompt
        
        # Check for persona marker
        assert "You are ASTA, Karthik's personal AI assistant" in system_prompt, "Persona marker line not found in assembled prompt"
        
        # Check for the recalled fact
        assert fact_text in system_prompt, (
            f"real recall() did not surface the seeded Mongo fact into the assembled "
            f"system prompt: {system_prompt!r}"
        )
        
        # Check order (persona before memory)
        persona_idx = system_prompt.find("You are ASTA")
        memory_idx = system_prompt.find(fact_text)
        assert persona_idx < memory_idx, "Persona block must appear before memory context"
        
        assert call_1_args[1] == FrameDirection.DOWNSTREAM

        assert call_2_args[0] is user_frame
        assert call_2_args[1] == FrameDirection.DOWNSTREAM
    finally:
        await db_manager.db["insights"].delete_many({"session_id": session_id})
