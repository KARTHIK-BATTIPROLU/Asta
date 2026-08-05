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

## ITERATION 5
G1: PASS 
G2: PASS
G3: PASS (Memory call sites mapped)
G4: PASS (AstaSessionDB adapter implemented and routes to MemoryEngine)
G5: PASS (state.db creation verified disabled via real test)
G6: BLOCKED-ENV: OPENAI_API_KEY (Needs key to run Hermes reasoning loop)
G7: BLOCKED-ENV: OPENAI_API_KEY (Needs key for end-to-end text seam)
G8: PASS (Persona injection point wired at `hermes_agent/agent/prompt_builder.py:DEFAULT_AGENT_IDENTITY`)
G9: BLOCKED-ENV: OPENAI_API_KEY (Needs key to check skill parity)
G10: PASS (Integration contract written to `HERMES_INTEGRATION_CONTRACT.md`)
Task attacked this iteration: G6, G8, G10. Found missing `concurrent-log-handler` and installed it. Found missing `OPENAI_API_KEY` for Gate 6. Replaced `DEFAULT_AGENT_IDENTITY` in `prompt_builder.py` with Asta's persona for Gate 8. Wrote the integration contract for Gate 10.
Commit: Pending
Regressions found on re-check: None
Blocked items: G6, G7, G9 blocked on `OPENAI_API_KEY`
Files and Lines mapped:
- `hermes_agent/hermes_state.py`: Core `SessionDB` logic (all SQLite/FTS5 persistence).
- `hermes_agent/run_agent.py:2254`: `self._session_db.append_messages_batch(`
- `hermes_agent/run_agent.py:7744`: `db.get_conversation_root(`
- `hermes_agent/agent/context_compressor.py:5780`: `session_db.archive_and_compact(`
- `hermes_agent/agent/conversation_compression.py:3195`: `agent._session_db.archive_and_compact(`
- `hermes_agent/tools/session_search_tool.py:705`: `db.search_messages(`
- `hermes_agent/tools/react_to_message_tool.py:29`: `SessionDB()` initialization
- `hermes_agent/agent/trace_upload.py:341`: `db.get_messages_as_conversation(`
Commit: Pending
Regressions found on re-check: None
Blocked items: None
