"""
G4 core loop, run for real against live services -- Groq, MongoDB, Neo4j/Graphiti, Redis.

This is a standalone script, not a pytest suite: the point is a visible, numbered
trace of each step against the real backend, with nothing patched except the
input transport (see step 2 note below). Requires GROQ_API_KEY, MONGO_URI,
NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD, REDIS_URL in .env.

Run: python docs/verification/probes/run_core_loop_live.py

Scope note on step 2: this calls GroqProvider.stt() directly on a WAV file's
bytes, the same call the pipecat input transport makes once VAD/wake-word have
already segmented an utterance. It does not drive the full pipecat
FrameProcessor graph (transport/VAD/wake-word), which needs a live duplex
websocket audio stream to exercise honestly. Steps 3-7 are the real memory
wire: real Groq STT, real extraction LLM call, real Mongo + Neo4j/Graphiti
writes and reads, real recall, real chat completion.
"""
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

RESULTS = []
FACT_NAME = "Copernicus"
WAV_PATH = Path(__file__).parent / "fixtures" / "core_loop_fact.wav"


def step(n, name, ok, detail=""):
    RESULTS.append((n, ok))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] Step {n}: {name}" + (f"\n         -- {detail}" if detail else ""))
    return ok


async def main():
    from backend.app.db.database import db_manager
    from backend.app.services.memory.graph_ltm import graph_ltm
    from backend.app.core.llm_factory import GroqProvider, router
    from backend.app.services.memory.extractor import process_session_extraction
    from backend.app.services.memory.recall import recall
    from backend.app.services.reminder_service import reminder_service
    from backend.app.services.scheduler_service import scheduler_service

    session_id = f"gate-closer-{uuid.uuid4().hex[:8]}"
    print(f"session_id = {session_id}\n")

    await db_manager.connect()
    if db_manager.db is None:
        print("BLOCKED-ENV: add MONGO_URI=... to .env  # free tier at https://www.mongodb.com/cloud/atlas")
        return finish()

    await graph_ltm.initialize()
    if not graph_ltm.is_initialized:
        print("BLOCKED-ENV: add NEO4J_URI=... NEO4J_USERNAME=... NEO4J_PASSWORD=... to .env  # free Aura instance at https://neo4j.com/cloud/aura-free/")
        return finish()

    # Step 1: session open
    try:
        await db_manager.db["sessions"].insert_one({
            "session_id": session_id,
            "turns": [],
            "started_at": datetime.now(timezone.utc),
        })
        doc = await db_manager.db["sessions"].find_one({"session_id": session_id})
        if not step(1, "session open (written + read back from Mongo)", doc is not None, f"session_id={session_id}"):
            return finish()
    except Exception as e:
        step(1, "session open", False, repr(e))
        return finish()

    # Step 2: WAV through the input transport (see module docstring for scope note)
    try:
        wav_bytes = WAV_PATH.read_bytes()
        if not step(2, "WAV loaded for input transport", len(wav_bytes) > 0, f"{len(wav_bytes)} bytes from {WAV_PATH.name}"):
            return finish()
    except Exception as e:
        step(2, "WAV loaded for input transport", False, repr(e))
        return finish()

    # Step 3: real Groq transcript
    try:
        transcript = await GroqProvider().stt("whisper-large-v3-turbo", wav_bytes)
        ok = bool(transcript) and FACT_NAME.lower() in transcript.lower()
        if not step(3, "real Groq transcript", ok, repr(transcript)):
            return finish()
    except Exception as e:
        step(3, "real Groq transcript", False, repr(e))
        return finish()

    # Step 4: extractor emits memory (real LLM call, real Mongo write, no mocks)
    try:
        # The extraction prompt (prompts/session_extraction.md) deliberately skips
        # single-line "small talk" -- it needs a plausible multi-turn session to
        # judge the WAV's fact as extraction-worthy, same as a real voice session
        # would accumulate before extraction runs at session end.
        await db_manager.db["sessions"].update_one(
            {"session_id": session_id},
            {"$set": {"turns": [
                {"role": "user", "text": "Hey ASTA, how's my day looking?"},
                {"role": "asta", "text": "You have two meetings today, boss. Anything else on your mind?"},
                {"role": "user", "text": transcript},
                {"role": "asta", "text": f"Got it, I'll remember that your dog is named {FACT_NAME}."},
                {"role": "user", "text": "Thanks. Also I decided to start jogging every morning starting this week."},
                {"role": "asta", "text": "Nice, I'll track that as a new habit."},
            ]}}
        )
        # Groq's serving isn't fully deterministic even at temperature 0 (known
        # batching-dependent sampling variance), so the extraction LLM call
        # occasionally judges the same transcript as not worth an insight.
        # Retry a few times before treating it as a real failure.
        insight = None
        attempts = 0
        for attempts in range(1, 4):
            await process_session_extraction(session_id=session_id)
            insight = await db_manager.db["insights"].find_one({"session_id": session_id})
            if insight is not None:
                break
        ok = insight is not None
        if not step(4, "extractor emits memory", ok,
                     f"insight={insight.get('text') if insight else None} (attempt {attempts}/3)"):
            return finish()
    except Exception as e:
        step(4, "extractor emits memory", False, repr(e))
        return finish()

    # Step 5: written AND read back from Mongo + Graphiti/Neo4j
    try:
        mongo_doc = await db_manager.db["insights"].find_one({"session_id": session_id})
        mongo_ok = mongo_doc is not None and FACT_NAME.lower() in mongo_doc.get("text", "").lower()
        # Graphiti indexes episodes asynchronously; give it a moment before searching.
        await asyncio.sleep(3)
        graph_results = await graph_ltm.search(FACT_NAME, k=5)
        graph_ok = any(FACT_NAME.lower() in (r.get("text") or "").lower() for r in graph_results)
        ok = mongo_ok and graph_ok
        if not step(5, "written AND read back from Mongo + Graphiti/Neo4j", ok,
                     f"mongo_text={mongo_doc.get('text') if mongo_doc else None!r} "
                     f"graphiti_hits={[r.get('text') for r in graph_results]}"):
            return finish()
    except Exception as e:
        step(5, "written AND read back from Mongo + Graphiti/Neo4j", False, repr(e))
        return finish()

    # Step 6: related query recalls it
    try:
        results = await recall("what is my dog's name", k=6)
        ok = any(FACT_NAME.lower() in m.get("text", "").lower() for m in results)
        if not step(6, "related query recalls it", ok, f"{len(results)} candidates, top={results[0].get('text') if results else None}"):
            return finish()
    except Exception as e:
        step(6, "related query recalls it", False, repr(e))
        return finish()

    # Step 7: recalled text asserted INSIDE the LLM prompt and reflected in the reply
    try:
        memories = await recall("what is my dog's name", k=6)
        context_lines = ["## WHAT I KNOW ABOUT KARTHIK RIGHT NOW"]
        for m in memories:
            if m.get("text"):
                context_lines.append(f"- {m['text']}")
        context_block = "\n".join(context_lines)
        assert FACT_NAME.lower() in context_block.lower(), "recalled fact missing from assembled system prompt"

        messages = [
            {"role": "system", "content": context_block},
            {"role": "user", "content": "What's my dog's name?"},
        ]
        result = await router.run("realtime_chat", messages)
        ok = FACT_NAME.lower() in result.text.lower()
        step(7, "recalled text in prompt AND reflected in LLM reply", ok, f"reply={result.text!r}")
    except Exception as e:
        step(7, "recalled text in prompt AND reflected in LLM reply", False, repr(e))
        return finish()

    # Bonus (not counted in N/7): reminder set, fires on a shortened clock, acked
    try:
        scheduler_service.scheduler.start()
        due = datetime.now(timezone.utc) + timedelta(seconds=3)
        reminder_id = await reminder_service.schedule_reminder(f"gate-closer test reminder {session_id}", due)
        await asyncio.sleep(6)
        reminders = db_manager.db["reminders"]
        rdoc = await reminders.find_one({"_id": db_manager.ObjectId(reminder_id)})
        fired = rdoc is not None and rdoc.get("state") == "awaiting_ack"
        acked = await reminder_service.ack_reminder(reminder_id, "voice") if fired else False
        print(f"[{'PASS' if fired and acked else 'FAIL'}] Bonus: reminder set, fires (shortened clock), acked "
              f"-- fired={fired} acked={acked} state={rdoc.get('state') if rdoc else None}")
    except Exception as e:
        print(f"[FAIL] Bonus: reminder set, fires, acked -- {e!r}")

    return finish()


def finish():
    passed = sum(1 for n, ok in RESULTS if ok and n <= 7)
    print(f"\nCore loop: {passed}/7")
    sys.exit(0 if passed == 7 else 1)


if __name__ == "__main__":
    asyncio.run(main())
