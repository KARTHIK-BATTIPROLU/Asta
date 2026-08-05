# ASTA × HERMES INTEGRATION STATE

## RECONNAISSANCE FINDINGS

### Asta's Memory Adapter
Asta's memory is orchestrated via a clean singleton in `memory/memory_engine.py` (`MemoryEngine` class).
Key methods that Hermes needs to route to:
- `get_context_for_session(session_id: str, user_input: str, workflow_type: str) -> Dict`
- `on_user_message(session_id: str, message: str) -> None`
- `save_session(session_id: str, workflow_type: str, messages: List[Dict], start_time: str, notion_page_id: str = "") -> bool`
- `remember(content: str, tags: List[str]) -> Dict`
- `recall(query: str) -> List[Dict]`

### Hermes's Memory Structure
Hermes uses an internal SQLite database with FTS5 for full-text search.
Memory access is **scattered inline (harder swap)**. It is not behind a clean interface/adapter class; instead, state is tightly coupled to SQLite operations in:
- `hermes_state.py` (Main SQLite State Store handling WAL mode, compression, FTS5)
- `run_agent.py` handles the invocation in methods like `_persist_session`, `_flush_messages_to_session_db`, and `_get_session_db_for_recall`.

### Hermes's Text I/O Seam
The entry point for receiving a text input and producing a text output is located in `run_agent.py`:
- `chat(self, message: str, stream_callback: Optional[callable] = None) -> str`
This is where Asta's STT/TTS will plug in.

### Hermes's Skill/Tool System
Hermes has a native skill system organized into modular directories under `skills/` (e.g., `skills/productivity/`, `skills/note-taking/`, `skills/email/`).
Tools are orchestrated by `toolsets.py` and `model_tools.py`. This confirms native support exists before deprecating Asta's bespoke integrations.

---

## ITERATION 2
G1: PASS 
G2: PASS (Merged Hermes core deps into requirements.txt, resolved pymongo and redis pin conflicts)
G3..G10: FAIL (Not yet started)
Task attacked this iteration: G2, merged `hermes_agent/pyproject.toml` dependencies into Asta's `requirements.txt`. 
Changes made to version pins:
- Changed `pymongo==4.9.0` to `pymongo>=4.12,<4.17` because Asta's `langgraph-checkpoint-mongodb==0.4.0` dependency strictly required it.
- Changed `redis==5.1.0` to `redis>=7.1.0` because Asta's environment had `falkordb 1.6.2` installed which required a newer redis-py client.
Commit: Pending
Regressions found on re-check: None
Blocked items: None
