# Hermes Integration Contract

This document defines the strict programmatic boundaries between the Asta outer shell and the Hermes inner reasoning core.

## 1. Memory Adapter Interface (`AstaSessionDB`)
Hermes's native memory is completely disabled. All persistence calls from Hermes's internal agents route through `hermes_agent.asta_memory_bridge.AstaSessionDB`.

This duck-typed adapter intercepts Hermes's memory operations and routes them to Asta's `memory.memory_engine.MemoryEngine`.

### Required Methods
The `AstaSessionDB` class MUST implement the following interface to satisfy Hermes's orchestration loop:

```python
class AstaSessionDB:
    # Called on every turn to push user/assistant messages to the L0 active buffer
    def append_message(self, session_id: str, role: str, content: str, **kwargs) -> int: ...
    def append_messages_batch(self, session_id: str, messages: List[Dict[str, Any]]) -> tuple[int, int]: ...
    def replace_messages(self, session_id: str, messages: List[Dict[str, Any]], **kwargs) -> None: ...
    
    # Called by Hermes to hydrate context for reasoning
    def get_messages(self, session_id: str, **kwargs) -> List[Dict[str, Any]]: ...
    def get_messages_as_conversation(self, session_id: str, **kwargs) -> List[Dict[str, Any]]: ...
    
    # Called periodically by Hermes to save a summary/compacted transcript. 
    # Routes to `MemoryEngine.save_session()`.
    def archive_and_compact(self, session_id: str, compacted_messages: List[Dict[str, Any]], **kwargs) -> None: ...
    
    # Hermes aux endpoints (Duck-typed to return [] / False / None)
    def search_messages(self, query: str, **kwargs) -> List[Dict[str, Any]]: ...
    def search_sessions(self, query: str, **kwargs) -> List[Dict[str, Any]]: ...
    def has_archived_messages(self, session_id: str) -> bool: ...
```

## 2. Text-Only Seam (I/O Boundaries)

Asta exclusively handles Voice input/output (STT/TTS). Hermes is strictly text-only and must be invoked using its standard conversational API.

### Input to Hermes
Asta feeds the transcribed voice string into Hermes via:
```python
from hermes_agent.run_agent import AIAgent

agent = AIAgent(session_id="asta-session-id", provider="openai", model="gpt-4o")
# The transcribed text is passed to chat()
response_text = agent.chat("Transcribed user input string here")
```

### Output from Hermes
Hermes returns a single text string (the assistant's response) from the `chat()` call. Asta then takes this string and routes it to the TTS pipeline.

## 3. Persona Injection Point

Asta's persona is injected at the deepest level of Hermes's prompt scaffolding to ensure it persists across turns and context compressions.

**Injection Site:** `hermes_agent/agent/prompt_builder.py` 
**Constant:** `DEFAULT_AGENT_IDENTITY`

This constant is embedded in the `stable_parts` of the system prompt constructed by `hermes_agent/agent/system_prompt.py:build_system_prompt_parts()`.
