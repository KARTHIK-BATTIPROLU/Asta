import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.db.database import db_manager
from backend.app.services.memory.extractor import ExtractionSchema, InsightSchema, EmotionSchema, process_session_extraction
from backend.app.services.memory.outbox import enqueue_extraction
from backend.app.voice.session_store import create_session, append_turn


def _mock_extraction_result():
    return ExtractionSchema(
        insights=[
            InsightSchema(
                kind="fact",
                text="User likes testing.",
                entities=["testing"],
                confidence=0.9,
                evidence="stated in conversation",
            )
        ],
        priority_signals=[],
        contradictions=[],
        emotional_state=EmotionSchema(overall="neutral", notable_moments=[]),
        open_loops=[],
    )


async def _ensure_mongo():
    await db_manager.connect()
    if db_manager.db is None:
        pytest.skip("MONGO_URI not configured")
    # Guard against mock pollution from other tests in the same run
    if not hasattr(db_manager.db, "sessions"):
        await db_manager.connect()


@pytest.mark.asyncio
async def test_enqueue_on_session_with_user_turn():
    await _ensure_mongo()
    session_id = f"outbox-test-{uuid.uuid4().hex[:8]}"
    await create_session(session_id)
    await append_turn(session_id, "user", "Hello ASTA")

    ok = await enqueue_extraction(session_id)
    assert ok is True

    pending = await db_manager.db["outbox"].count_documents({
        "kind": "extract",
        "payload.session_id": session_id,
        "status": "pending",
    })
    assert pending == 1

    await db_manager.db["outbox"].delete_many({"payload.session_id": session_id})
    await db_manager.db["sessions"].delete_one({"session_id": session_id})


@pytest.mark.asyncio
async def test_enqueue_idempotent():
    await _ensure_mongo()
    session_id = f"outbox-idem-{uuid.uuid4().hex[:8]}"
    await create_session(session_id)
    await append_turn(session_id, "user", "Repeat me")

    assert await enqueue_extraction(session_id) is True
    assert await enqueue_extraction(session_id) is False

    pending = await db_manager.db["outbox"].count_documents({
        "kind": "extract",
        "payload.session_id": session_id,
        "status": "pending",
    })
    assert pending == 1

    await db_manager.db["outbox"].delete_many({"payload.session_id": session_id})
    await db_manager.db["sessions"].delete_one({"session_id": session_id})


@pytest.mark.asyncio
async def test_worker_drains_pending_task():
    await _ensure_mongo()
    session_id = f"outbox-drain-{uuid.uuid4().hex[:8]}"
    await create_session(session_id)
    await append_turn(session_id, "user", "Extract this fact about chess.")

    await db_manager.db["outbox"].insert_one({
        "kind": "extract",
        "status": "pending",
        "payload": {"session_id": session_id},
        "ts": datetime.now(timezone.utc),
        "attempts": 0,
    })

    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=_mock_extraction_result())
    mock_llm.with_structured_output.return_value = mock_structured

    with patch("backend.app.services.memory.extractor.llm_factory.get_model", return_value=mock_llm):
        with patch("backend.app.services.memory.extractor.graph_ltm.is_initialized", False):
            # Run one iteration of the worker loop manually
            outbox = db_manager.db["outbox"]
            task = await outbox.find_one_and_update(
                {"status": "pending", "kind": "extract", "payload.session_id": session_id},
                {"$set": {"status": "processing"}},
            )
            assert task is not None
            await process_session_extraction(session_id)
            await outbox.update_one({"_id": task["_id"]}, {"$set": {"status": "done"}})

    doc = await outbox.find_one({"payload.session_id": session_id})
    assert doc["status"] == "done"

    insights = await db_manager.db["insights"].count_documents({"session_id": session_id})
    assert insights >= 1

    await db_manager.db["insights"].delete_many({"session_id": session_id})
    await db_manager.db["outbox"].delete_many({"payload.session_id": session_id})
    await db_manager.db["sessions"].delete_one({"session_id": session_id})


@pytest.mark.asyncio
async def test_private_session_skipped_by_extractor():
    await _ensure_mongo()
    session_id = f"outbox-private-{uuid.uuid4().hex[:8]}"
    await db_manager.db["sessions"].insert_one({
        "session_id": session_id,
        "private": "no_extract",
        "turns": [{"role": "user", "text": "Secret fact that must not be stored."}],
    })

    await process_session_extraction(session_id)

    insights = await db_manager.db["insights"].count_documents({"session_id": session_id})
    assert insights == 0

    # Private session should not enqueue
    ok = await enqueue_extraction(session_id)
    assert ok is False

    await db_manager.db["sessions"].delete_one({"session_id": session_id})


@pytest.mark.asyncio
async def test_enqueue_skips_empty_session():
    await _ensure_mongo()
    session_id = f"outbox-empty-{uuid.uuid4().hex[:8]}"
    await create_session(session_id)

    ok = await enqueue_extraction(session_id)
    assert ok is False

    pending = await db_manager.db["outbox"].count_documents({"payload.session_id": session_id})
    assert pending == 0

    await db_manager.db["sessions"].delete_one({"session_id": session_id})
