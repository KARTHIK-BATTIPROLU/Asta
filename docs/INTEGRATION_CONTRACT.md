# ASTA Integration Contract — updated 2026-07-16 by gate-closer session

Every claim below cites the file:line it comes from. Where a signal a bridge
would need (orb state) didn't exist in the code yet, it was added at the
natural pipeline point (see "Orb state events") and covered by a test in
`docs/verification/probes/test_orb_state_events.py`. This document describes
the engine as it exists right now, for whoever wires Ultron/Friday to it next.

## WS endpoint

**`GET/WS /ws/conversation`** — `backend/app/api/ws_transport.py:42`

Query param `trigger` (default `"manual"`) selects the pipeline variant — see
`backend/app/voice/pipeline.py:136` (`build_pipeline`); `trigger="wake_word"`
inserts a `ServerWakeWordConfirmProcessor` stage
(`backend/app/voice/pipeline.py:147-149`), `trigger="morning_alarm"` injects a
one-time morning-verification system message on the first turn
(`backend/app/voice/pipeline.py:69-81`).

### Auth handshake
`backend/app/auth/token_auth.py:60` (`verify_ws_token_and_device`), called at
`ws_transport.py:45` before `websocket.accept()`:
1. Bearer token: read from the `token` query param, or an `Authorization:
   Bearer <token>` header if the query param is absent
   (`token_auth.py:63-69`). Compared with `hmac.compare_digest` against
   `settings.ASTA_API_BEARER_TOKEN` (`token_auth.py:74`).
2. Device binding: `device_id` query param, or `X-Device-Id` header
   (`token_auth.py:71-72`), must match the single row in the
   `registered_devices` Mongo collection (`token_auth.py:82-86`) — this
   backend supports exactly one paired device at a time.
3. Failure at either step closes the socket with code `1008` and no message
   (`ws_transport.py:46`) — the client learns nothing more specific than "the
   handshake failed."
4. Success updates `registered_devices.last_seen` in the background
   (`token_auth.py:89-92`), accepts the socket, and sends the first message on
   the connection: `{"type": "orb_state", "state": "idle"}`
   (`ws_transport.py:53`, added this session — see below).

### Message schemas
Frames are pipecat `Frame` objects internally; what actually crosses the wire
is whatever the transport serializes (raw PCM in, WAV-framed PCM/TTS audio out
— `FastAPIWebsocketParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000,
add_wav_header=True)`, `ws_transport.py:58-63`) plus the JSON control messages
below, all sent via `broadcast_message()` (`ws_transport.py:16-25`, best-effort
fan-out to every connection in `_active_connections`):

| type | payload | emitted from |
|---|---|---|
| `orb_state` | `{"type": "orb_state", "state": "idle"\|"listening"\|"thinking"\|"speaking"}` | see next section |
| `status` (legacy, unused) | `{"type": "status", "status": "listening"\|"thinking"\|"speaking", "turn_id": ...}` | `backend/app/api/turn_processor.py:80,223,242,744` — this handler is **not mounted** (grepped the whole tree; only its `fetch_memory_context` helper is imported elsewhere, `backend/app/api/routes.py:22`). Dead code today; `orb_state` is the live schema. |
| `asta_proactive` | `{"type": "asta_proactive", "trigger": "morning_alarm"\|"night_planning", "response": str, "audio_needed": true}` | `backend/app/main.py:404-409` (morning alarm callback), `:428-433` (night planning callback) |
| reminder speak | `{"t": "speak", "text": str, "requires_ack": true, "reminder_id": str}` | `backend/app/services/reminder_service.py:103-108`, fires when `_active_connections` is non-empty and outside the silent window |

## Orb state events

`idle | listening | thinking | speaking` did not exist anywhere in the active
pipeline before this session (confirmed by grep: `backend/api/turn_processor.py`
has a same-shaped `status` field but isn't mounted; `TTSService`'s own
`push_start_frame`/`push_stop_frames` flags default to `False` —
`venv/Lib/site-packages/pipecat/services/tts_service.py:153,155` — so no
speaking/idle signal was ever emitted either). Added four small, real,
tested emission points:

| state | emitted from | trigger |
|---|---|---|
| `idle` | `backend/app/api/ws_transport.py:53` | connection just authenticated, before any turn |
| `idle` | `backend/app/voice/pipeline.py:134` (`LanguageSplitTTS.run_tts`, after the yield loop) | TTS playback for the turn has finished |
| `listening` | `backend/app/voice/pipeline.py:41-44` (`VadOrbNotifier.process_frame`) | pipecat's `VADProcessor` unconditionally pushes `VADUserStartedSpeakingFrame` the instant Silero detects speech onset (`venv/Lib/site-packages/pipecat/processors/audio/vad_processor.py:69-75`); `VadOrbNotifier` sits directly after `vad` in the pipeline (`pipeline.py:152-153`), before STT has any chance to consume the frame |
| `thinking` | `backend/app/voice/pipeline.py:66` (`RouterLLMService.process_frame`, on receiving a `TranscriptionFrame`) | fires before the morning-brief/research-intent checks and the actual `router.run(...)` call, so it covers the full "user's turn is in, LLM hasn't answered yet" window |
| `speaking` | `backend/app/voice/pipeline.py:131` (`LanguageSplitTTS.run_tts`, before the yield loop) | TTS is about to start producing audio for the turn |

All four go through `_emit_orb_state()` (`backend/app/voice/pipeline.py:22-29`),
a thin wrapper around `ws_transport.broadcast_message` that swallows any
broadcast failure — a client UI update is never worth failing the pipeline
over. Tested in `docs/verification/probes/test_orb_state_events.py` (3
tests: `VadOrbNotifier` forwards frames and fires on `VADUserStartedSpeakingFrame`,
`RouterLLMService` fires `thinking` on transcription, `LanguageSplitTTS` fires
`speaking` then `idle` around the TTS generator).

Not yet wired: there's no `VADUserStoppedSpeakingFrame` → any-state transition
(e.g. straight to `thinking` the moment the user stops talking, ahead of STT
finishing) — right now `thinking` only fires once `RouterLLMService` sees the
finished `TranscriptionFrame`, so there's a `listening`→`thinking` gap covering
STT latency with no distinct state. A hosted bridge that wants a "transcribing"
state would add it at `backend/app/voice/pipeline.py:152` the same way
`VadOrbNotifier` was added.

## Streaming events

| event | frame / mechanism | file:line |
|---|---|---|
| Partial transcript | **none** | `GroqWhisperSTT.run_stt` (`backend/app/voice/stt.py:19-29`) is a single batch Whisper call per VAD-segmented utterance — it yields one final `TranscriptionFrame`, never an interim/partial one. A bridge wanting live partials would need a streaming STT provider, not the current one. |
| Reflex filler | `TTSSpeakFrame(filler)` pushed immediately on a high-cost query, ahead of the real LLM reply | `backend/app/voice/reflex.py:66` (`ReflexProcessor.process_frame`); cost heuristic + filler phrase pool at `reflex.py:11-55` |
| TTS audio frames | `run_tts` yields whatever `EdgeTTSService.run_tts` produces (pipecat's own TTS audio frame stream) | `backend/app/voice/pipeline.py:128-134` (`LanguageSplitTTS.run_tts`) |
| Final text | `TextFrame(res.text)` bracketed by `LLMFullResponseStartFrame`/`LLMFullResponseEndFrame` | `backend/app/voice/pipeline.py:102,107,113` (`RouterLLMService.process_frame`, non-research branch) |

## REST endpoints

Mounted routers and their prefixes, from `backend/app/main.py:75-86`:

| method + path | file:line | auth |
|---|---|---|
| `GET /api/health` | `backend/app/api/routes.py:44` | none |
| `GET /api/health/circuits` | `backend/app/api/routes.py:77` | none |
| `POST /api/device/register` | `backend/app/api/routes.py:88` | bearer (`verify_bearer`) |
| `POST /api/admin/reset/circuit/{circuit_name}` | `backend/app/api/routes.py:119` | bearer+device |
| `POST /api/chat` → `ChatRequest{message, voice_enabled, session_id?, workflow_hint?}` → `ChatResponse{session_id, reply, audio_base64?}` | `backend/app/api/routes.py:130` (schemas `:31-41`) | bearer+device |
| `POST /api/device-token` | `backend/app/api/routes.py:189` | bearer+device |
| `POST /api/trigger/morning-brief` | `backend/app/api/routes.py:212` | bearer+device |
| `POST /api/sync/batch` | `backend/app/api/routes.py:254` | bearer+device |
| `POST /api/metrics/daily` | `backend/app/api/routes.py:315` | bearer+device |
| `GET /api/preferences/` , `GET/PUT /api/preferences/{pref_type}` , `POST /api/preferences/{pref_type}/voice` | `backend/app/api/preferences.py:126,28,54,93` | see file |
| `GET /api/content/calendar/{platform}`, `POST .../add`, `GET /api/content/linkedin/posts`, `POST .../approve`, `POST .../schedule`, `DELETE .../{row_id}`, `GET /api/content/logs/{platform}`, `POST /api/content/seed-calendar` | `backend/app/api/content.py:30,65,99,114,132,156,174,205` | see file |
| `GET /api/health/` (public), `GET /api/health/deep`, `/memory`, `/scheduler`, `/llm`, `/services` (bearer) | `backend/app/api/health.py:17,27,107,125,159,190` | mixed, see file |
| `POST /api/settings/silent` | `backend/app/api/settings_routes.py:14` | see file |
| `POST /api/v1/sync` | `backend/app/api/sync_routes.py:20` | see file |
| `GET /api/me` | `backend/app/main.py:89` | bearer+device |
| `GET /api/ngrok-url` | `backend/app/main.py:94` | none |
| `GET /health/memory` (note: root-level, no `/api` prefix) | `backend/app/main.py:136` | none |
| `POST /v1/chat/completions` (OpenAI-compatible adapter, streaming SSE) | `backend/app/main.py:156` | bearer+device |

Two things worth flagging for whoever builds on this next: `GET /api/health`
(`routes.py:44`) and `GET /api/health/` (`health.py:17`, mounted under the same
`/api` prefix) are two independently-implemented handlers answering
overlapping paths — pick one before a bridge starts depending on either.
`backend/app/api/health_routes.py` and `backend/app/api/metrics_routes.py`
define routers that are never `include_router`'d anywhere (grepped) — dead
code, not part of the live surface.

## Persona injection point

**`backend/app/services/llm_service.py:10`** (`get_system_prompt`) is where
persona + mood + memory actually combine today, feeding
**`get_hydrated_messages`** (`llm_service.py:87`) which builds the full
messages array for **`stream_llm_response`** (`llm_service.py:109`) — the
function behind the OpenClaw-facing `/v1/chat/completions` adapter
(`backend/app/main.py:156-212`):

1. **Persona** — the `ASTA_PERSONALITY` block, hardcoded at `llm_service.py:12-17`.
2. **Mood** — `mode_notice`, derived from the `health_status` argument
   (`"full"` / `"local_only"` / `"degraded_l3"` / `"degraded_l2_l3"`,
   `llm_service.py:19-25`) — today this reflects *system* degradation, not an
   emotional mood; a Friday-style mood axis would slot in as another
   `mode_notice`-shaped string appended the same way.
3. **Memory context** — the `memory_context` argument, appended verbatim
   right after the persona block (`llm_service.py:31-32`), before the fixed
   behavioral rules/examples block (`llm_service.py:35-83`).

A Friday-style persona block would replace or extend `ASTA_PERSONALITY` at
`llm_service.py:12`; mood would extend the `mode_notice` branch at
`llm_service.py:19-25`; memory stays exactly where it is — this function
already accepts it as a parameter.

Note: this is the text/OpenClaw-bridge path. The voice pipeline has a
*separate*, simpler injection point — `MemoryContextInjector`
(`backend/app/voice/memory_injector.py:16-59`) builds a `SystemPromptUpdateFrame`
containing *only* the memory block (no persona, no mood) and
`RouterLLMService.process_frame` (`backend/app/voice/pipeline.py:55-62`)
installs it as `messages[0]`, replacing whatever was there. A persona block
does not currently reach the voice path at all — wiring one in means either
seeding `RouterLLMService.messages[0]` with a persona+memory string before
`MemoryContextInjector` ever fires, or changing `MemoryContextInjector` to
call `get_system_prompt()` instead of building its own bare context block.

### Worked example
Calling the real function:

```python
from backend.app.services.llm_service import get_system_prompt
get_system_prompt(health_status="full", memory_context="- Karthik has a dog named Copernicus.")
```

produces (persona block, then the memory line slotted in verbatim, then the
fixed behavioral rules — full output, unedited):

```
You are ASTA — Karthik's personal AI brain.
Personality: Gen-Z, cheerful, funny, occasionally sarcastic. Always call him "boss".
In research/deep work mode: professional, focused, thorough.
In casual conversation: chill, witty, supportive.
Keep voice responses to 1-3 sentences max unless asked for detail.
Never say "I cannot" — find a way or ask a clarifying question.

- Karthik has a dog named Copernicus.

PERSONALITY:
- Casual and friendly for greetings and small talk
- Direct and efficient for tasks
- Proactive with tools - if you can use a tool to help, DO IT
- No filler phrases like "Based on our previous conversations" or "Nothing to report"
- Match Karthik's energy: casual gets casual, serious gets serious

EXAMPLES OF GOOD RESPONSES:
...
Remember: Be helpful, be natural, be proactive. You're ASTA, not a formal assistant.
```

(`...` elides the fixed few-shot examples block, unchanged by any argument —
see `llm_service.py:44-82` for the full text.)
