"""
Stage 3 proof for the L3/L4 memory granularity fix.

Scenario: one session, 3 turns, 3 distinct facts. Verifies each turn gets its
own L3 vector + L4 document (no overwrite), and that a LATER session can
retrieve facts from EARLIER turns (not just the last one).

Run from the repo root: python -m memory.granularity_proof
"""
import asyncio
import logging
from datetime import datetime
from uuid import uuid4

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from memory.memory_engine import memory_engine
from memory.l3_vectors import l3_vectors
from memory.l4_store import l4_store
from backend.app.core.supervisor_graph import CHAT_SYSTEM
from backend.app.core.llm_factory import acomplete

PASS = []
FAIL = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        PASS.append(name)
        print(f"PASS - {name} {detail}")
    else:
        FAIL.append(name)
        print(f"FAIL - {name} {detail}")


async def main():
    print("Connecting memory layers...")
    status = await memory_engine.connect_all()
    print(status)

    session_a = f"granfix-A-{uuid4().hex[:8]}"
    session_new1 = f"granfix-B-{uuid4().hex[:8]}"
    session_new2 = f"granfix-C-{uuid4().hex[:8]}"
    session_unknown = f"granfix-D-{uuid4().hex[:8]}"
    session_research = f"granfix-R-{uuid4().hex[:8]}"

    facts = [
        "Hey, just so you know -- my friend Suresh runs the design club at college.",
        "Also, the certificate-gen project I'm building uses React for the frontend.",
        "One more thing: I want to post about AI agents on LinkedIn this Friday.",
    ]

    # ── BEFORE counts ────────────────────────────────────────────────
    before_total_l4 = await l4_store.db.sessions.count_documents({})
    asta_memory_db = l4_store.client.get_database("asta_memory")
    before_asta_memory = await asta_memory_db.sessions.count_documents({})
    try:
        before_l3_stats = await asyncio.to_thread(l3_vectors.index.describe_index_stats)
        before_l3_total = before_l3_stats.total_vector_count
    except Exception as e:
        before_l3_total = None
        print(f"L3 stats unavailable: {e}")

    print(f"\nBEFORE: asta_db.sessions total={before_total_l4}, "
          f"asta_memory.sessions={before_asta_memory}, "
          f"L3 total_vector_count={before_l3_total}\n")

    # ── 3 turns, cumulative messages (mirrors supervisor_graph.save_session) ──
    conv = []
    for i, fact in enumerate(facts, start=1):
        conv.append({"role": "user", "content": fact})
        conv.append({"role": "assistant", "content": "Got it, noted boss."})
        ok = await memory_engine.save_session(
            session_id=session_a,
            workflow_type="general",
            messages=list(conv),
            start_time=datetime.utcnow().isoformat(),
        )
        check(f"Turn {i} save_session returns True", ok)

    # ── AFTER: L4 should now have 3 distinct docs for session_a ─────────
    docs = await l4_store.db.sessions.find(
        {"session_id": session_a}, {"_id": 0, "turn_id": 1, "summary": 1}
    ).to_list(length=None)
    turn_ids = [d.get("turn_id") for d in docs]
    check("3 distinct L4 docs for session_a", len(docs) == 3, f"(got {len(docs)})")
    check("3 distinct non-empty turn_ids", len(set(turn_ids)) == 3 and all(turn_ids),
          f"(turn_ids={turn_ids})")

    for d in docs:
        print(f"  turn_id={d.get('turn_id')} summary={str(d.get('summary'))[:140]!r}")

    after_total_l4 = await l4_store.db.sessions.count_documents({})
    check("asta_db.sessions grew by 3", after_total_l4 == before_total_l4 + 3,
          f"(before={before_total_l4}, after={after_total_l4})")

    after_asta_memory = await asta_memory_db.sessions.count_documents({})
    check("asta_memory.sessions unchanged (single pipeline)", after_asta_memory == before_asta_memory,
          f"(before={before_asta_memory}, after={after_asta_memory})")

    # ── L3: each turn's vector exists distinctly (give Pinecone a moment) ──
    await asyncio.sleep(3)
    vector_ids = [f"{session_a}:{tid}" for tid in turn_ids]
    try:
        fetch_res = await asyncio.to_thread(l3_vectors.index.fetch, ids=vector_ids)
        found = getattr(fetch_res, "vectors", {}) or {}
        check("3 distinct L3 vectors fetchable by id", len(found) == 3, f"(found {list(found.keys())})")
    except Exception as e:
        check("3 distinct L3 vectors fetchable by id", False, f"error: {e}")

    # ── NEW SESSION: ask about FIRST fact (Suresh / design club) ──
    ctx1 = await memory_engine.get_context_for_session(
        session_id=session_new1,
        user_input="Who runs the design club, again?",
        workflow_type="general",
    )
    formatted1 = memory_engine.format_context_for_prompt(ctx1)
    print(f"\n--- Retrieval for FIRST fact (new session {session_new1}) ---\n{formatted1}\n")
    check("First fact (Suresh/design club) retrieved in NEW session",
          "suresh" in formatted1.lower() or "design club" in formatted1.lower())

    # ── NEW SESSION: ask about MIDDLE fact (certificate-gen / React) ──
    ctx2 = await memory_engine.get_context_for_session(
        session_id=session_new2,
        user_input="What frontend framework does the certificate-gen project use?",
        workflow_type="general",
    )
    formatted2 = memory_engine.format_context_for_prompt(ctx2)
    print(f"\n--- Retrieval for MIDDLE fact (new session {session_new2}) ---\n{formatted2}\n")
    check("Middle fact (React/certificate-gen) retrieved in NEW session",
          "react" in formatted2.lower() or "certificate" in formatted2.lower())

    # ── REGRESSION: recall still refuses a genuinely unknown fact ──
    ctx3 = await memory_engine.get_context_for_session(
        session_id=session_unknown,
        user_input="What is the name of my pet goldfish?",
        workflow_type="general",
    )
    formatted3 = memory_engine.format_context_for_prompt(ctx3)
    system = CHAT_SYSTEM
    if formatted3.strip():
        system = f"{CHAT_SYSTEM}\n\n{formatted3}"
    answer = await acomplete(system, "What is the name of my pet goldfish?", task="quick", max_tokens=100)
    print(f"\n--- Unknown-fact answer ---\n{answer}\n")
    refused = any(p in answer.lower() for p in
                  ["don't have", "do not have", "no record", "not sure", "don't know", "no information", "not on record"])
    check("Unrelated/unknown fact still honestly refused", refused, f"(answer={answer!r})")

    # ── REGRESSION: research workflow_type still writes a per-turn record ──
    ok_r = await memory_engine.save_session(
        session_id=session_research,
        workflow_type="research",
        messages=[
            {"role": "user", "content": "Find me papers about retrieval-augmented generation."},
            {"role": "assistant", "content": "Sure, I'll look into RAG papers for you."},
        ],
        start_time=datetime.utcnow().isoformat(),
    )
    check("research workflow_type save_session returns True", ok_r)
    r_docs = await l4_store.db.sessions.find(
        {"session_id": session_research}, {"_id": 0, "turn_id": 1}
    ).to_list(length=None)
    check("research workflow_type wrote 1 L4 doc with turn_id",
          len(r_docs) == 1 and bool(r_docs[0].get("turn_id")), f"(docs={r_docs})")

    # ── SUMMARY ──
    print("\n" + "=" * 60)
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED CHECKS:")
        for f in FAIL:
            print(f"  - {f}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
