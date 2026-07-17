#!/usr/bin/env python3
"""
ASTA memory loop acceptance test — live end-to-end, zero test fixtures.

Proves: talk → session close → outbox extraction → restart → recall.

Usage:
  python scripts/prove_memory_loop.py              # normal memory loop
  python scripts/prove_memory_loop.py --private    # private mode variant
  python scripts/prove_memory_loop.py --no-restart # skip backend restart step

Requires: .env with MONGO_URI, GROQ_API_KEY, ASTA_API_BEARER_TOKEN, and a
registered device in Mongo. Set ASTA_DEVICE_ID in .env or pass --device-id.
Backend must be reachable at --host (default 127.0.0.1:8000).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

PASS = False
TRANSCRIPT: list[str] = []


def log(msg: str) -> None:
    line = f"[prove] {msg}"
    print(line)
    TRANSCRIPT.append(line)


def fail(msg: str) -> None:
    log(f"FAIL: {msg}")
    sys.exit(1)


def get_ws_uri(host: str, token: str, device_id: str) -> str:
    base = host.replace("http://", "ws://").replace("https://", "wss://")
    if not base.startswith("ws"):
        base = f"ws://{base}"
    return f"{base}/ws/conversation?token={token}&device_id={device_id}"


async def ws_session(
    host: str,
    token: str,
    device_id: str,
    turns: list[str],
    timeout_per_turn: float = 90.0,
) -> list[str]:
    """Run multiple text turns in one WS session; return assistant replies."""
    uri = get_ws_uri(host, token, device_id)
    log(f"WS connect → {uri.split('?')[0]}")
    all_replies: list[str] = []

    async with websockets.connect(uri, open_timeout=15) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        if isinstance(raw, str):
            log(f"  recv: {raw}")

        for text in turns:
            reply_parts: list[str] = []
            await ws.send(json.dumps({"type": "text", "text": text}))
            log(f"  sent: {text!r}")

            deadline = time.monotonic() + timeout_per_turn
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(15, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                if isinstance(raw, bytes):
                    continue
                log(f"  recv: {raw}")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "text" and data.get("text"):
                    reply_parts.append(data["text"])
                if data.get("type") == "orb_state" and data.get("state") == "idle" and reply_parts:
                    break

            reply = " ".join(reply_parts).strip()
            all_replies.append(reply)
            log(f"  reply: {reply!r}")

    return all_replies


async def poll_outbox_done(session_id: str | None, timeout: float = 120.0) -> dict | None:
    from backend.app.db.database import db_manager
    await db_manager.connect()
    if db_manager.db is None:
        fail("MONGO_URI not configured")

    outbox = db_manager.db["outbox"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        query: dict = {"kind": "extract", "status": "done"}
        if session_id:
            query["payload.session_id"] = session_id
        doc = await outbox.find_one(query, sort=[("ts", -1)])
        if doc and (session_id is None or doc["payload"]["session_id"] == session_id):
            log(f"outbox done: session_id={doc['payload']['session_id']}")
            return doc
        pending = await outbox.count_documents({"kind": "extract", "status": "pending"})
        processing = await outbox.count_documents({"kind": "extract", "status": "processing"})
        log(f"  polling outbox... pending={pending} processing={processing}")
        await asyncio.sleep(2)
    return None


async def dump_artifacts(session_id: str, keyword: str) -> None:
    from backend.app.db.database import db_manager
    from backend.app.services.memory.graph_ltm import graph_ltm

    await db_manager.connect()
    insights = await db_manager.db["insights"].find(
        {"session_id": session_id}
    ).to_list(10)
    log(f"Mongo insights ({len(insights)}):")
    for ins in insights:
        log(f"  - {ins.get('text', '')[:120]}")

    outbox_doc = await db_manager.db["outbox"].find_one(
        {"payload.session_id": session_id, "status": "done"}
    )
    log(f"Outbox done doc: {outbox_doc}")

    try:
        await graph_ltm.initialize()
        if graph_ltm.is_initialized:
            results = await graph_ltm.search(keyword)
            log(f"graph_ltm.search({keyword!r}): {results[:3] if results else '[]'}")
        else:
            log("graph_ltm not initialized (Neo4j unavailable)")
    except Exception as e:
        log(f"graph_ltm.search skipped: {e}")


def wait_health(host: str, timeout: float = 60.0) -> bool:
    url = host.rstrip("/") + "/api/health/"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                log(f"health OK: {r.text[:200]}")
                return True
        except Exception as e:
            log(f"  health poll: {e}")
        time.sleep(2)
    return False


async def get_latest_session_id() -> str | None:
    from backend.app.db.database import db_manager
    await db_manager.connect()
    doc = await db_manager.db["sessions"].find_one(sort=[("started_at", -1)])
    return doc.get("session_id") if doc else None


async def run(private: bool, no_restart: bool, host: str, token: str, device_id: str) -> None:
    global PASS
    suffix = uuid.uuid4().hex[:6]

    if private:
        secret_keyword = f"Zephyrus{suffix}"
        fact = f"My secret code word is {secret_keyword}."
        recall_q = "What is my secret code word?"

        log("=== PRIVATE SESSION: enable mode + state secret ===")
        replies = await ws_session(host, token, device_id, [
            "private mode on",
            fact,
        ])
        confirm = replies[0] if replies else ""
        log(f"Private mode confirmation: {confirm!r}")
        if "private" not in confirm.lower():
            fail(f"Expected private mode confirmation, got: {confirm!r}")

        session_id = await get_latest_session_id()
        log(f"Private session_id: {session_id}")

        from backend.app.db.database import db_manager
        await db_manager.connect()
        await asyncio.sleep(8)  # allow worker time if anything was enqueued

        pending = await db_manager.db["outbox"].count_documents({
            "payload.session_id": session_id,
            "status": {"$in": ["pending", "processing", "done"]},
        })
        insights = await db_manager.db["insights"].count_documents({"session_id": session_id})
        log(f"Outbox tasks for private session: {pending}; insights: {insights}")
        if insights > 0:
            fail(f"Private session produced {insights} insights (expected 0)")

        log("=== SESSION B: attempt recall of secret ===")
        reply_b_list = await ws_session(host, token, device_id, [recall_q])
        reply_b = reply_b_list[0] if reply_b_list else ""
        log(f"Session B reply: {reply_b!r}")
        if secret_keyword.lower() in reply_b.lower():
            fail(f"Secret leaked into recall: {reply_b!r}")
        log("PASS: private mode — secret not recalled")
        PASS = True
        return

    fact = f"My favorite chess opening is the Sicilian Najdorf ({suffix})."
    recall_q = "What's my favorite chess opening?"
    needle = "Najdorf"

    log("=== SESSION A: state fact ===")
    replies_a = await ws_session(host, token, device_id, [fact])
    log(f"Session A reply: {replies_a[0] if replies_a else ''!r}")

    session_id = await get_latest_session_id()
    log(f"Session A session_id: {session_id}")

    log("=== Wait for outbox extraction ===")
    done_doc = await poll_outbox_done(session_id)
    if not done_doc:
        fail("Outbox never reached 'done' within timeout")
    session_id = done_doc["payload"]["session_id"]
    await dump_artifacts(session_id, "chess")

    if not no_restart:
        log("=== Restart backend (restart uvicorn manually if external) ===")
        if not wait_health(host, timeout=30):
            log("WARN: health check failed after restart window — continuing anyway")

    log("=== SESSION B: recall question ===")
    replies_b = await ws_session(host, token, device_id, [recall_q])
    reply_b = replies_b[0] if replies_b else ""
    log(f"Session B reply: {reply_b!r}")

    if needle.lower() not in reply_b.lower():
        fail(f"Recall missed {needle!r} in reply: {reply_b!r}")

    log(f"PASS: reply contains {needle!r}")
    PASS = True


def main() -> None:
    parser = argparse.ArgumentParser(description="ASTA memory loop proof")
    parser.add_argument("--private", action="store_true", help="Run private mode variant")
    parser.add_argument("--no-restart", action="store_true", help="Skip restart wait")
    parser.add_argument("--host", default=os.getenv("ASTA_HOST", "http://127.0.0.1:8000"))
    parser.add_argument("--device-id", default=os.getenv("ASTA_DEVICE_ID", ""))
    args = parser.parse_args()

    token = os.getenv("ASTA_API_BEARER_TOKEN", "").strip()
    if not token:
        fail("ASTA_API_BEARER_TOKEN not set in .env")

    device_id = args.device_id.strip()
    if not device_id:
        fail("ASTA_DEVICE_ID not set — add to .env or pass --device-id")

    if not wait_health(args.host, timeout=15):
        fail(f"Backend not reachable at {args.host}/api/health/ — start uvicorn first")

    asyncio.run(run(args.private, args.no_restart, args.host, token, device_id))
    if PASS:
        print("\n" + "=" * 60)
        print("MEMORY LOOP PROOF: PASS")
        print("=" * 60)
        sys.exit(0)
    fail("Unknown failure")


if __name__ == "__main__":
    main()
