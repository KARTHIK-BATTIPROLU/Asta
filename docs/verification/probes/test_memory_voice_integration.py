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
async def test_memory_voice_integration_real_wire():
    """
    True integration test: seed a real fact via the real write path
    (memory_handler.store_insight against a real Mongo collection with a
    real local embedding), run the real recall() (nothing patched), and
    assert the fact lands in the system prompt MemoryContextInjector
    assembles for the LLM. No external LLM call is on this path (recall()
    only does local embedding + Mongo/Graphiti lookups), so nothing here
    is mocked except the pipecat push_frame sink used to capture output.
    """
    await db_manager.connect()
    if db_manager.db is None:
        pytest.skip("MONGO_URI not configured -- cannot run the real memory wire test")

    session_id = f"wire-test-{uuid.uuid4().hex[:8]}"
    fact_text = f"Karthik keeps his spare keys under the doormat (wire-test {uuid.uuid4().hex[:6]})."
    embedding = await _generate_embedding(fact_text)

    stored = await memory_handler.store_insight(
        session_id=session_id,
        kind="fact",
        text=fact_text,
        entities=["keys"],
        confidence=0.95,
        embedding=embedding,
        pinned=False,
    )
    assert stored, "setup: failed to write the seed fact via the real store_insight path"

    try:
        injector = MemoryContextInjector()
        injector.push_frame = AsyncMock()

        user_frame = TranscriptionFrame(text="Where did I put my keys?", user_id="karthik", timestamp="now")
        await injector.process_frame(user_frame, FrameDirection.UPSTREAM)

        injector.push_frame.assert_called()

        call_1_args = injector.push_frame.call_args_list[0][0]
        call_2_args = injector.push_frame.call_args_list[1][0]

        assert isinstance(call_1_args[0], SystemPromptUpdateFrame)
        assert fact_text in call_1_args[0].system_prompt, (
            f"real recall() did not surface the seeded Mongo fact into the assembled "
            f"system prompt: {call_1_args[0].system_prompt!r}"
        )
        assert call_1_args[1] == FrameDirection.UPSTREAM

        assert call_2_args[0] is user_frame
        assert call_2_args[1] == FrameDirection.UPSTREAM
    finally:
        await db_manager.db["insights"].delete_many({"session_id": session_id})
