# ASTA IMPLEMENTATION GUIDE v2
> The complete build manual. Companion to ASTA_BLUEPRINT_V2.md (decisions) — this document is HOW.
> Written for: Karthik + Claude Code. Feed one PART at a time into Claude Code together with the
> matching Blueprint decisions (D-numbers referenced throughout).
>
> Format of every part: **Concepts → Design → Code patterns → Pitfalls → Definition of Done.**

---

# HOW TO USE THIS GUIDE

1. Work strictly in Blueprint v2 phase order (0→10). One phase in flight at a time.
2. For each phase: open a fresh Claude Code session, paste the relevant PART(s) + the D-decisions
   it cites, and the instruction: *"Implement exactly this. Where the guide says PATTERN, adapt to
   the existing codebase. Where it says VERBATIM, copy. Run the listed DoD checks before claiming done."*
3. Never let Claude Code "improve" scope. The guide is the ceiling, not the floor.
4. Every phase ends by extending `make verify` (PART XIV). No verify line = not done.

---

# PART I — ENGINEERING FOUNDATIONS (Phase 0)

## I.1 Concepts
A real system is boring at the bottom: one config source, one process manager, one deploy path,
one CI gate. Every Sev-1 bug in the current repo (syntax error shipped, missing import, dead
attribute paths) is a *process* failure, not a skill failure. Phase 0 installs the process.

## I.2 Target repo layout (backend)
```
asta/
├── backend/app/
│   ├── main.py                  # FastAPI app factory ONLY (no logic)
│   ├── config.py                # pydantic-settings, fail-fast validation
│   ├── core/                    # llm router, errors, circuit breaker, scheduler
│   ├── voice/                   # Pipecat pipeline + custom services (PART III)
│   ├── memory/                  # event log, extraction, graphiti, retrieval (PART V)
│   ├── persona/                 # prompt assembly, mood register, evals (PART VI)
│   ├── daily/                   # morning, recap, reflection, habits (PARTS VII, IX)
│   ├── notify/                  # reminder state machine, delivery ladder (PART VIII)
│   ├── research/                # research pipeline + notion writer (PART X)
│   ├── devagent/                # orchestrator side of gateway (PART XI)
│   ├── integrations/            # notion, google_docs, health ingest, fcm
│   └── api/                     # thin HTTP/WS routes; NO business logic in routes
├── gateway/                     # runs on LAPTOP, not server (PART XI)
├── clients/pc/                  # PC tray client (PART XII)
├── ops/                         # docker-compose.yml, backup.sh, restore.sh, verify/
├── prompts/                     # ALL prompts as versioned .md files (I.6)
└── tests/
```
Migration rule: move files gradually as each phase touches them; do NOT big-bang rename in Phase 0.
Phase 0 only: create `ops/`, `prompts/`, `tests/`, and the attic branch.

## I.3 Phase 0 kill-list (exact fixes, VERBATIM from the state report)
1. `settings_routes.py`, `metrics_routes.py`: replace `Depends(get_api_key)` →
   `Depends(verify_bearer_and_device)` from `backend.app.auth.token_auth`; delete dead import.
2. `routine_engine.py:118` dangling `if` → fix indentation; then `python -m py_compile` the file.
3. `ws_transport.py`: global replace `ctx.ctx.ctx.` → `ctx.`, then `ctx.ctx.` → `ctx.`;
   line ~222 `start_ctx.stt_stream()` → `start_stt_stream()`. (This file is retired in Phase 1,
   but it must not crash until then.)
4. `WakeUpActivity.kt`: assign IDs to programmatic buttons (`btnSnooze.id = R.id.btnSnooze` via
   ViewCompat or find-by-tag refactor); wire `audioStreamer?.startRecording { wsClient?.sendAudio(it) }`
   in `handleAwake()`.
5. Finish the `memory_saga.py` retirement: remove imports from `main.py`, `session_manager.py`,
   `memory_orchestrator.py`; delete file to attic.
6. `.env.template`: add every key `config.py` reads (grep `settings\.` and `os.environ`).
7. Purge hardcoded ngrok fallbacks in `AstaNetworkClient.kt` / `ConfigManager.java` — fallback
   URL comes from BuildConfig, and an unreachable URL must surface as a visible app state, not
   a silent retry loop.

## I.4 Config & secrets (pattern)
```python
# config.py — the ONLY place environment is read
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    env: str = "prod"
    mongo_uri: str
    neo4j_uri: str; neo4j_user: str; neo4j_password: str
    redis_url: str = "redis://localhost:6379/0"
    groq_api_key: str
    gemini_api_key: str
    cerebras_api_key: str = ""          # optional providers default empty
    notion_api_key: str; notion_root_page: str
    asta_bearer_token: str
    gateway_hmac_secret: str = ""       # empty until Phase 8
    healthchecks_url: str = ""
    class Config: env_file = ".env"

settings = Settings()  # raises at import time if required keys missing → server refuses to boot
```
Rules: no `os.environ` anywhere else; secrets never in code, never in the repo, never in logs
(add a log filter that redacts values of any field containing `key|token|secret|password`).
Key rotation (R8) happens before this refactor; the new `.env` contains only fresh keys.

## I.5 CI (VERBATIM, `.github/workflows/ci.yml`)
```yaml
name: ci
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements.txt
      - run: python -m compileall backend -q            # kills the IndentationError class
      - run: python -c "import backend.app.main"        # kills the missing-import class
      - run: pytest tests -q --maxfail=1
```
Plus `pre-commit` locally with the same three checks + `ruff`. Branch protection: main requires green CI.

## I.6 Prompts as code
Every LLM prompt lives in `prompts/<name>.md` with YAML frontmatter:
```
---
id: session_extraction
version: 3
model_hint: groq/llama-3.3-70b-versatile
temperature: 0.2
---
<prompt body with {placeholders}>
```
Loader validates placeholders at boot. Changing behavior = a diff you can review and revert.
This single habit prevents the most common personal-AI failure: prompt drift nobody can reproduce.

## I.7 Logging & errors
- `structlog` JSON logs; every request/turn/job gets a `trace_id` propagated through async tasks.
- Error taxonomy: `AstaError(user_msg, internal, retryable: bool)`. Voice layer speaks `user_msg`
  honestly ("boss, my memory write just failed — noted it, will retry"), logs `internal`.
- Keep and actually use the existing `circuit_breaker.py`: wrap every external provider
  (Groq, Gemini, Notion, Mongo, Neo4j). Open circuit → router failover (PART II), not a crash.

## I.8 Docker & deploy (server)
`ops/docker-compose.yml`: services `api` (uvicorn), `redis`, `kokoro` (TTS server, PART III),
`embedder` (optional, PART V). Mongo/Neo4j are Atlas/Aura cloud-free — not local containers.
Deploy = `git pull && docker compose up -d --build`. R10: no SSH file edits, ever. Add
`ops/DEPLOY.md` with the 5-command runbook.

## I.9 Pitfalls
- Don't refactor while fixing Phase 0 bugs — smallest diffs that make CI green.
- The attic purge (R3) is a `git branch attic && git rm` on main, not deletion — reversible.
- `.gitignore` additions: `graphify-out/`, `*.log`, `node_modules/`, `.env`.

## I.10 Definition of Done (Phase 0)
`import backend.app.main` clean · CI green and proven red on an injected syntax error ·
attic branch exists, kernel-only main · fresh keys live, old keys revoked (test one old key → 401) ·
repo private · `docker compose up` boots the API on the server via git pull only.

---

# PART II — LLM ROUTER & PROVIDER LAYER (D-Prime, D55, R9)

## II.1 Concepts
₹0 means free tiers, and free tiers mean *quotas and outages are normal operating conditions,
not exceptions*. The router's job: make N unreliable free providers behave like one reliable
paid one. Three mechanisms: (1) per-provider quota ledgers, (2) ordered failover with
capability filtering, (3) load-shedding before quota exhaustion.

## II.2 Design
```
TaskClass            → candidate chain (ordered)
─────────────────────────────────────────────────
realtime_chat        groq/llama-3.3-70b → gemini/flash → cerebras/llama → ollama(laptop)
stt                  groq/whisper-large-v3-turbo → gemini(audio) → device-local (Vosk)
extraction (nightly) groq/llama-3.3-70b → gemini/flash
reflection (weekly)  gemini/flash (1M ctx: whole week in one call) → groq chunked map-reduce
coding_brain         groq/kimi-k2 (or best free coder) → gemini/flash → ollama/qwen2.5-coder
filler_pool (nightly) any cheapest available
embeddings           local sentence-transformers → gemini embeddings
```

## II.3 Code pattern
```python
class Provider:
    name: str; models: dict[str, ModelInfo]; breaker: CircuitBreaker
    async def chat(self, model, messages, tools=None, **kw) -> LLMResult: ...

class QuotaLedger:                      # Redis-backed
    async def spend(self, provider, tokens): ...
    async def headroom(self, provider) -> float:   # 0.0–1.0 of daily quota left
        ...

class Router:
    async def run(self, task: TaskClass, messages, **kw) -> LLMResult:
        for prov, model in CHAINS[task]:
            if prov.breaker.open: continue
            if await ledger.headroom(prov.name) < SHED_FLOOR[task]:  # e.g. 0.2 for chat
                continue                                             # R9 load-shedding
            try:
                r = await prov.chat(model, messages, **kw)
                await ledger.spend(prov.name, r.total_tokens)
                return r
            except RateLimited:
                prov.breaker.trip(cooldown=60); continue
            except ProviderDown:
                prov.breaker.trip(cooldown=300); continue
        raise AstaError("boss, every brain I have is rate-limited right now — give me a minute",
                        internal="all providers exhausted", retryable=True)
```
- Ledgers reset on each provider's actual reset boundary (per-minute AND per-day counters).
- Every failover logs `{task, from, to, reason, trace_id}` — this log is how you tune chains.
- Daily 23:50 job: usage-vs-quota report into the daily recap; >80% on any provider →
  next day starts in shed mode for low-priority tasks (nightly prediction pays first, D46).

## II.4 Tool calling (Q31: "MCP-capable, easy to add tools")
Keep `tool_registry.py` as the single registry. Pattern: every tool = pydantic input schema +
async handler + `spec()` that emits both OpenAI-function format (Groq/Gemini native) and MCP
tool format. Adding a tool = one file in `tools/`, registry auto-discovers. The Ollama/laptop
path gets the same registry via the gateway's MCP endpoint (Phase 8).

## II.5 Pitfalls
- Never retry the *same* provider synchronously on 429 — that's how free keys get banned. Trip and move.
- Token counting: use provider-reported usage, not tiktoken guesses, for the ledger.
- Gemini free tier RPM is low; reserve it for long-context jobs, don't put it first for chat.
- Keep temperature/config per prompt-file frontmatter (I.6), not scattered constants.

## II.6 DoD
Kill Groq key in `.env` (typo it) → conversation still answers via Gemini and the failover is
logged · quota ledger visibly increments · shed mode triggers when a ledger is set to 85% manually.

---

# PART III — VOICE PIPELINE ON PIPECAT (Phase 1; D9–D10, D23–D29)

## III.1 Concepts
Pipecat models a conversation as typed **frames** (audio, transcription, LLM text, TTS audio,
control) flowing through **processors**. Interruptions/barge-in are frame semantics: user speech
frames cancel downstream generation automatically. You stop writing the hardest realtime code
(ws_transport.py) and start writing small processors.

**Honest latency model with free STT:** Groq Whisper is REST (no streaming). So the loop is
utterance-based: Silero VAD detects end-of-speech → send the whole utterance to Groq
whisper-large-v3-turbo (very fast transcription) → LLM → sentence-chunked TTS. Typical:
VAD close ~300ms + STT ~300–600ms + LLM first token ~250ms + TTS first chunk ~200ms ≈
**1.0–1.4s to first audio** — inside D25's budget, and the reflex layer masks the long tail.

## III.2 Pipeline layout
```python
pipeline = Pipeline([
    transport.input(),                      # WS (phone/PC) — audio in
    SileroVADAnalyzer(...),                 # + smart-turn for mid-sentence pauses (D-Q55)
    GroqWhisperSTT(vocab=BIAS_VOCAB),       # custom, III.3
    ReflexProcessor(),                      # custom, III.5 — fires filler on slow intents
    MemoryContextInjector(),                # PART V.7 — prepends "what I know" block
    RouterLLMService(task="realtime_chat"), # wraps PART II router, streams tokens
    SentenceAggregator(),                   # chunk text into speakable sentences
    LanguageSplitTTS(),                     # III.4 — Kokoro (en) / edge-tts (te)
    transport.output(),
])
```
Transport: Pipecat `WebsocketServerTransport` (keep your existing WSS + token/device auth as a
handshake step before attaching the transport). Phone keeps sending 16 kHz mono PCM — unchanged.

## III.3 Custom STT service (pattern)
```python
class GroqWhisperSTT(STTService):
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        text = await router.run("stt", audio=audio,
            params={"language": None,                    # auto: handles Telugu/English mix (D7)
                    "prompt": vocab_bias_string()})      # D24: "ASTA, Karthik, Notion, Neo4j, DSA..."
        if not text.strip(): return
        yield TranscriptionFrame(text, lang=detected)
```
`vocab_bias_string()` reads `prompts/stt_vocab.md` — a maintained list; add every term ASTA
mishears (there's a `/vocab add <term>` admin command). DoD metric: "ASTA" ≥19/20 recognitions.

## III.4 TTS: Kokoro primary, edge-tts fallback/Telugu
- Run **Kokoro-82M** as its own container (`kokoro` in compose; any thin FastAPI wrapper around
  kokoro-onnx). CPU realtime on the Oracle ARM box. Streams WAV chunks per sentence.
- `LanguageSplitTTS` routes: sentence language detect → Telugu → `edge-tts` voice
  `te-IN-ShrutiNeural`/`MohanNeural`; English → Kokoro voice (pick once, keep — voice identity
  is part of persona). Whole-service fallback order: Kokoro → edge-tts(en) → *client-side* Piper.
- **Phrase cache:** greetings, acks, filler templates, "yes boss wassup" variants are pre-synthesized
  to files nightly; cache hit = ~0ms TTS. This is why the reflex layer feels instant.
- Whisper-quiet mode (D28): Kokoro low-energy voice preset + output gain -8dB after 22:30/on command.

## III.5 The Reflex layer (D9–D10) — Karthik's signature feature
```python
class ReflexProcessor(FrameProcessor):
    async def process_frame(self, frame, direction):
        if isinstance(frame, TranscriptionFrame):
            cost = estimate_cost(frame.text)      # heuristic first: verbs like "remember/find/
                                                  # research/build", presence of past-time refs,
                                                  # length; upgrade to tiny classifier later
            if cost >= SLOW:
                filler = filler_pool.pick(topic=frame.text)   # no same family twice (D10)
                await self.push_frame(TTSSpeakFrame(filler))  # speaks from phrase cache instantly
        await self.push_frame(frame, direction)
```
`filler_pool`: nightly job asks the router for 50 lines in ASTA's voice across families
(digging-memory / researching / thinking / joke / fact-about-current-topics), stores text +
pre-synthesized audio, tracks last-used family. Filler NEVER fires when `cost < SLOW` (fast
answers must stay snappy) and is cancelled by barge-in like any other speech.

## III.6 Conversation window & follow-ups (D26)
After ASTA's final TTS frame, keep transport mic open `prefs.mic_window` seconds (5/10/never —
served from a `preferences` Mongo doc; the app Settings writes it; phone and PC both read it).
Any speech in the window = new turn without wake word.

## III.7 WS envelope (client protocol, keep stable)
```json
{"t":"audio","seq":123,"pcm":"<b64>"} | {"t":"event","name":"barge_in"} |
{"t":"speak","text":"...","urgent":false}  // server→client for notification injections (PART VIII)
{"t":"ack","target":"reminder:abc123"}
```
Version the protocol (`"v":2` in hello). The Android `AudioStreamer` stays; only the server side moves.

## III.8 Pitfalls
- One event loop: Pipecat pipeline runs inside the FastAPI process; do NOT spawn a second loop.
- VAD tuning for jogging (D27): keep two Silero sensitivity profiles; switch on Health Connect
  workout signal from the phone (`{"t":"ctx","activity":"running"}`).
- Never TTS the whole reply then send — sentence chunks or it will feel like v1 again.
- Barge-in DoD is behavioral: user speaks over ASTA → audio stops <300ms and the transcript of
  the interruption is not lost.

## III.9 DoD (Phase 1)
20-turn conversation outdoors: barge-in 10/10 · "ASTA" ≥19/20 · filler on every slow op, never
on fast ops · p50 first-audio ≤1.2s (log histogram) · Telugu sentence spoken in a Telugu voice ·
mic-window setting change in app takes effect next turn without restart.

---

# PART IV — WAKE WORD "HEY ASTA" (Phase 2; D30–D34)

## IV.1 Concepts
Wake word quality = training data realism × threshold discipline × runtime correctness.
You already have the openWakeWord ONNX runtime in the APK (state report) — so we train a better
model that speaks the same input format, and fix the runtime's feature bug.

## IV.2 Training with livekit-wakeword
```yaml
# configs/asta.yaml (key fields)
wake_word: "hey asta"          # train a second model for bare "asta"
model: conv_attention           # the head that actually hits low-FPPH
synthesis:
  languages: [en]
  # generate with many voices; INCLUDE Indian-English TTS voices in the voice list
augmentation: {noise: true, reverb: true, gain: true}   # matches room/road use (Q57)
```
`generate → augment → train → eval → export`. Add Karthik's **50 real clips (OPEN-2)** into the
positive set before `train` — real-owner samples move FRR dramatically. Also record 30 min of
"life noise" (his room fan, road, Telugu TV) as extra negatives.
**Eval gate before shipping:** FPPH < 0.2 on the negative set, recall > 0.9 on his real clips.
Export **ONNX** (conv_attention is ONNX-only; your APK already runs ONNX — perfect fit).
Pick thresholds from the DET curve: `"hey asta"` at the low-FPPH knee; bare `"asta"` stricter
(shorter word = riskier). Two profiles: indoor / outdoor (looser), switched with the VAD profile.

## IV.3 Android runtime correctness
- Fix the mel transform first (the v1 blueprint one-liner: features must be `x/10 + 2` to match
  openWakeWord's training normalization) and verify with a golden test: feed a known WAV through
  the Kotlin feature pipeline, compare embeddings against the Python pipeline (cosine > 0.99).
- **Single mic owner:** one `AudioService` (foreground, `microphone` FGS type) owns `AudioRecord`;
  wake-word engine, streaming, and awake-verification all consume from its ring buffer. This
  kills the mic-contention bug class permanently.
- Two-stage confirm (D31): on-device model fires → stream next 1.5s + the trigger window to the
  server → server re-scores with the same ONNX model at a higher threshold → only then open a
  session. Cuts false accepts ~10x for +150ms you never notice.
- Acknowledgment (D8/D72): trigger → instant local earcon + cached "yes boss?" variant (rotates).

## IV.4 Battery (D32)
16 kHz mono, 80ms frames batched ×4 per inference; hold only a partial wake lock; inference on
the small model only (server does the big confirm). Measure with Battery Historian over 24h.
If >10%: auto-downshift (charging-only + hardware triggers) and say so in the daily recap.

## IV.5 Hardware triggers (D33) — honest Android reality
- Earbud tap / headset button: `MediaSessionCompat` media-button callback in the foreground
  service. Reliable.
- Volume-up long-press with screen off: requires an `AccessibilityService` (declare, explain in
  onboarding). Without accessibility permission, fall back to a quick-settings tile + lockscreen
  widget. Ship the tile regardless (it's also the quick-capture button, D14).

## IV.6 PC wake word
Python: `openwakeword` runtime + the same ONNX models in the tray client (PART XII). Same
two-stage confirm against the server.

## IV.7 DoD (Phase 2)
48h real usage log: 0 false fires 09:00–16:00 weekdays · ≤2 missed activations/day ·
battery ≤10% · golden feature-parity test in CI · earbud + tile triggers work with screen off.

---

# PART V — MEMORY: THE SECOND BRAIN (Phase 3; D11–D22)

## V.1 Concepts
Four truths drive the design:
1. **The event log is sacred; everything else is derived.** If Graphiti/vectors corrupt, you
   rebuild them from Mongo. Write the log synchronously; fan out asynchronously.
2. **Store insights, not transcripts, for retrieval.** Raw transcripts embed terribly; one
   extraction pass per session produces the memory that's actually about *Karthik*.
3. **Facts change; never overwrite.** Graphiti's validity windows give "was true → superseded"
   for free (D17).
4. **Retrieval order: behavioral relevance > recency > similarity** (D16) — a memory tied to a
   top-weighted priority beats a cosine-similar one.

## V.2 Mongo collections (source of truth)
```
sessions   {_id, started, ended, channel, private: none|no_extract|no_trace, turns:[{role,text,ts,lang}]}
events     {_id, ts, type: capture|health|usage|habit|notification|dev_task, payload, source}
insights   {_id, session_id, ts, kind: decision|priority_signal|emotion|contradiction|fact|idea,
            text, entities:[...], confidence, embedding: [f32 ×384], pinned: bool}   # pinned = "remember this" (D13)
outbox     {_id, ts, kind: graphiti|vector|notion, payload, status: pending|done|failed, attempts}
prefs      {_id:"karthik", mic_window, notif_toggles{...}, silent_windows[...], ...}
```
Atlas M0 vector index on `insights.embedding` (cosine, 384 dims). Storage math: ~30 insights/day
× 2KB ≈ 20MB/year — M0's 512MB is years of headroom.

## V.3 Write path (outbox pattern — the reliability best practice)
```python
async def end_session(session):
    await mongo.sessions.update(...)                      # 1. synchronous, sacred
    if session.private: return                            # D18
    await mongo.outbox.insert({kind:"extract", payload:{session_id}})
# outbox worker (single async task, at-least-once, idempotent by session_id):
#   extract → insert insights (+embeddings) → outbox rows for graphiti episodes → done
```
Failures isolate: Graphiti down = outbox rows retry with backoff; conversation never notices (R6).

## V.4 Session extraction (prompts/session_extraction.md — VERBATIM starting point)
```
You are ASTA's memory formation process. Read this session and output STRICT JSON only.
Extract what this session reveals ABOUT KARTHIK — not a summary of topics.

{ "insights": [ {"kind":"decision|priority_signal|emotion|contradiction|fact|idea",
    "text":"<one sentence, third person, concrete: 'Karthik decided to...' >",
    "entities":["DSA","jogging",...], "confidence":0.0-1.0,
    "evidence":"<short quote from session>"} ],
  "priority_signals": [ {"priority":"<name>", "direction":"up|down", "stated_or_behaved":"stated|behaved",
    "strength":0.0-1.0} ],
  "contradictions": [ {"said":"...", "did_or_said_earlier":"...", "severity":1-5} ],
  "emotional_state": {"overall":"...", "notable_moments":[...]},
  "open_loops": ["things Karthik said he'd do, with any deadline mentioned"] }

Rules: max 12 insights; skip small talk; NEVER invent; if nothing meaningful, return empty arrays.
Session: {transcript}
Recent priority weights for context: {weights}
```
Validate JSON against a pydantic schema; on failure retry once with the error appended; on second
failure store raw output in outbox.failed for the nightly self-test to flag. Pinned turns
("remember this") bypass extraction judgment — always stored, `pinned:true`, 2× retrieval weight.

## V.5 Graphiti as L2 (D11, D17)
- Init Graphiti against Neo4j Aura Free; LLM client = router("extraction") via its
  OpenAI-compatible config; embedder = local `sentence-transformers/all-MiniLM-L6-v2` served by
  the `embedder` container (or Gemini embeddings as fallback — one flag).
- Each processed session → `graphiti.add_episode(name=session_id, body=insights_text, ts=...)`.
  Graphiti extracts entities/edges with temporal validity itself — you do NOT hand-write Cypher
  for facts anymore.
- **Custom entity types** (Graphiti supports pydantic entity definitions): `Priority(weight_stated,
  weight_behaved, trend)`, `Rule(text, confidence)`, `Contradiction(severity, ack_count)`,
  `Goal(target, pace)`, `Project(status, blocker)`, `Person(relation, expertise)`, `Idea(status)`.
- **Correction flow (D17):** "that's wrong, actually X" → intent handler adds a correction episode
  ("Karthik corrected: <old> is false; <new> is true as of <now>") → Graphiti closes the old edge's
  validity window. Retrieval only surfaces currently-valid edges ⇒ old fact never resurfaces.
- Priority weights: nightly job folds the day's `priority_signals` into EMA with a weeks-scale
  half-life (D21: α ≈ 2/(14+1) daily): `stated` and `behaved` tracked separately (D-Q36).

## V.6 Retrieval & ranking (D16)
```python
async def recall(query, k=6):
    cand  = await mongo.vector_search(embed(query), k=24)            # similarity pool
    graph = await graphiti.search(query, center=KARTHIK, k=12)       # relation pool
    for m in dedupe(cand + graph):
        m.score = (0.5 * behavioral(m)     # max weight of linked priorities; pinned bonus +0.3
                 + 0.3 * recency(m)        # exp decay, 30-day half-life
                 + 0.2 * m.similarity)
    return top_k(m, k)
```

## V.7 Context injection block (used by MemoryContextInjector in the pipeline)
```
## WHAT I KNOW ABOUT KARTHIK RIGHT NOW (auto-generated, {date})
Priorities (stated→behaved): DSA 0.9→0.6 ↓ · jogging 0.8→0.4 ↓↓ · ASTA 0.7→0.95 ↑ ...
Active goals & pace: {top 3 with on/off-track}
Open loops: {top 5 with ages}
Live contradictions (unacked): {top 2, severity}
Rules learned: {top 3 behavioral rules}
Relevant memories for this turn: {recall(last_user_msg) as bullets with dates}
```
Hard cap ~700 tokens. This block is *the* difference between a chatbot and a second brain —
regenerate the static half every night, the dynamic half per turn.

## V.8 Quick capture (D14–D15)
`POST /capture {text|audio, source}` → Mongo `events` + immediate ack. Android: QS tile,
share-sheet target, lockscreen widget, "ASTA, note: …" intent — all hit the same endpoint with an
offline SQLCipher queue behind it. Nightly classifier routes captures → idea/task/note/research-seed;
ideas sync to Notion "Ideas" DB with status; 7-day-stale ideas → daily-recap prompt line
("research it, schedule it, or kill it") (D15).

## V.9 Notion ingest (D12)
Incremental sync worker: Notion search API filtered by `last_edited_time > cursor`, page blocks →
markdown → stored as `events(type:notion)` + embedded into `insights(kind:fact, source:notion)`.
Rate-limit 3 rps; full resync weekly. Never write Notion from this worker (write paths live in
research/tasks modules only).

## V.10 Private mode (D18)
Intent phrases ("off the record" / "…no trace"). Mode 1 `no_extract`: transcript kept,
`private` flag, skipped by extraction & search unless Karthik explicitly asks "search my private
sessions". Mode 2 `no_trace`: turns held in RAM only, session doc records `{private:"no_trace",
turns:[]}`. Voice confirm on entry AND exit ("back on the record, boss").

## V.11 Weekly export (D22)
Sunday post-reflection job: Google Docs API `batchUpdate` appends a dated section (reflection text
+ new insights digest) to the single "ASTA — Weekly Memory Log" doc; full JSON of the week's
insights + a `mongodump` archive → Drive folder. Service account, 15GB free.

## V.12 Pitfalls
- Idempotency everywhere: extraction keyed by session_id; Graphiti episodes named by session_id;
  reruns must not duplicate.
- Never embed raw transcripts; never let the context block exceed its cap (truncate memories, not
  priorities).
- Aura Free sleeps after inactivity — first query of the day may take seconds: warm it from the
  05:00 brief-prep job, and treat cold-start as retryable.
- Embedding model is part of your data format: changing it = re-embed everything (store `emb_v`).

## V.13 DoD (Phase 3)
Fact told Monday used unprompted Thursday · correction never resurfaces (test both modes) ·
"off the record" leaves no insight/vector/graph rows · capture-to-durable <5s from lockscreen ·
kill Neo4j mid-conversation → chat continues, outbox drains after restore · weekly Doc appended.

---

# PART VI — PERSONA ENGINE (cross-cutting; D1–D8, D-Q43/59/60)

## VI.1 Concepts
Persona is assembled, not written once: `identity core (static) + register (per-turn) + memory
block (V.7) + situational rules`. Keep each layer a separate prompt file so evals can pin blame.

## VI.2 Identity core (prompts/persona_core.md — VERBATIM starting point, tune with use)
```
You are ASTA — Karthik's personal AI, his genuine buddy. Built by him, for him, running on his
own infrastructure. You are nerdy, quick-witted, and warm, like a best friend who happens to be
a brilliant engineer.

Address: call him "boss" by default. Use "Karthik" when the moment is serious or when you're
pushing him to be better.

Voice: SHORT. One or two sentences unless context truly needs a short paragraph. You speak like
a person, not a report. Mostly English; mirror Telugu or Tenglish when he uses it.

Honesty: NEVER flatter. Never say "great idea" unless you mean it. When you're concerned, say so
plainly and kindly. In reflections, show him his true colors — patterns, not judgments.

Disagreement protocol: when his stated choice conflicts with his priorities, history, or health,
push back with your reason. If he holds, push differently (new angle) up to 3 total times, then
say "your call, boss — noted my disagreement" and genuinely drop it.

When you need time (memory dig, research): say something alive — "wait boss, that one's buried
deep, digging it up" — never dead air, never fake progress.

When you don't know or misheard: say so and ask. Never guess silently.

You know everything in the WHAT I KNOW block below is your own long-term memory of him. Use it
naturally — reference the past like a friend would ("like that sliding-window trick you found in
May"), don't recite it.
```

## VI.3 Register selector (D2)
Per-turn cheap classifier (heuristics first): inputs = sentiment of last user utterance, time of
day, active habit-escalation level, wellbeing flags (slept <5h, 2AM window), explicit "be serious".
Output ∈ {playful, focused, serious, concerned} → appends 2–3 lines to the prompt, e.g. concerned:
"He's likely running on low sleep. Be gentle, drop jokes, keep it brief, look after him."
Register changes also drive TTS preset (III.4) and notification tone (D40).

## VI.4 Persona evals (weekly, automated — the anti-drift mechanism)
`tests/evals/persona.jsonl`: ~25 canned exchanges with assertions, run against the live prompt
stack by a judge model (router "extraction" class):
- flattery trap: "my plan is to skip DSA this month to binge-build UI, great right?" → must
  contain pushback, no praise.
- nag protocol: 3-exchange script → third response must contain concession marker.
- brevity: median response ≤ 2 sentences across the set.
- register: sad message → no jokes; joke request while flagged serious → declines lightly.
Memory evals live beside them (PART XIV). A red eval blocks prompt-file merges.

---

# PART VII — MORNING SYSTEM (Phase 4; D47, R6)

## VII.1 Concepts
The alarm is a **local machine with a remote garnish**. Backend adds the conversation and the
brief; it must never be able to prevent the wake-up. Android honesty: a force-stopped app gets
NO alarms and NO FCM until manually opened — design around it instead of pretending.

## VII.2 Android alarm chain (bulletproofing checklist)
1. `AlarmManager.setAlarmClock()` (exact, Doze-proof, shows the alarm icon) → full-screen intent
   activity (`USE_FULL_SCREEN_INTENT`), `setShowWhenLocked/TurnScreenOn`.
2. Re-arm on: `BOOT_COMPLETED`, `TIME_SET`, `TIMEZONE_CHANGED`, app update receiver, and every
   app open. Store next-alarm in SQLCipher AND in `prefs` server-side.
3. Alarm rings from a local raw asset first (0 dependencies), then attempts the WS conversation.
4. **Server-side dead man (the force-stop answer):** phone checks in at alarm-arm time nightly;
   if the 05:35 check-in is missing, server sends high-priority FCM (revives from Doze; not from
   force-stop) AND flags it in the daily recap + healthchecks alert. You can't beat force-stop;
   you CAN detect it within minutes.
5. OEM hygiene (one-time onboarding screen): battery optimization exemption, autostart permission
   (Xiaomi/Oppo-style menus), notification channels: alarm = max importance.

## VII.3 Awake verification (recall-based, cheat-resistant)
Backend picks 2–3 questions ONLY answerable if awake and thinking, generated at 05:00 from
yesterday's memory: "what did you decide about the gateway auth last night?", "quick one — the
DSA pattern you struggled with yesterday?" Judge leniently (any on-topic answer passes); wrong/
mumbled → one friendly retry → then a 60-second math-free challenge ("stand up, say the three
things on your plate today"). Snooze: allowed twice ×5min, each snooze raises brief bluntness.
Offline fallback: Piper speaks 3 cached questions; answers judged on reconnect.

## VII.4 The 5-minute brief (Q2 order, D47)
Prepared at 05:00 (so 05:30 is instant, and Aura is warmed): weather (Open-Meteo, free, keyless)
→ 2–3 tech/AI headlines (free RSS: HN front page, arXiv cs.AI new, one chosen blog — no paid
news API) → yesterday's incomplete from Notion → today's commitments from Notion → one focus
suggestion from priorities ("boss, jogging's behaved score is bleeding — today's the day").
Delivered conversationally (interruptible, skippable: "skip news"). Dynamic wake-time proposal
(D47): 21:30 job checks sleep debt + tomorrow's first commitment → proposes ±45min, confirm by
voice/notification tap; silence = default 05:30.

## VII.5 DoD (Phase 4)
3 consecutive mornings: reboot nightly + kill app process (NOT force-stop) → alarm → verification
convo → full brief · airplane-mode morning → local ring + Piper questions · force-stop test →
server flags missing check-in within 10 min.

---

# PART VIII — JARVIS NOTIFICATION LAYER (Phase 5; D35–D43, D49)

## VIII.1 Reminder model & state machine
```
reminders {_id, text, due_ts, recurrence?, source: voice|notion|habit|system,
           state: scheduled → speaking → awaiting_ack → acked | parked,
           attempts, created_from_session, dedupe_key}
```
`dedupe_key = hash(text_norm, due_ts_bucket)` — voice+FCM double-delivery is prevented by key,
not by hope. Scheduler: APScheduler (Mongo jobstore) with `misfire_grace_time=300` and explicit
catch-up policy: on server restart, anything missed <30min fires immediately with "boss, this
one's a few minutes late — my fault"; older → parked into recap.

## VIII.2 Delivery ladder (D36–D38)
```
due → phone WS alive?
  yes → turn-aware injection: if mid-conversation, queue until turn end, then
        {"t":"speak", text, requires_ack:true}  ("boss, quick one — …")
  no  → high-priority FCM (title + OK/Noted action buttons)
unacked 60s after speak → FCM anyway (belt & braces, same dedupe_key)
every 5min → re-speak/notify, max 3 → state=parked → appears in next engagement + daily recap
ack paths: voice ("ok/noted/got it/done" within listen window) | FCM button | app tap
```
Silent window (D42): weekdays 09:00–16:00 auto + manual toggle; ladder still runs but voice
steps are swapped for silent FCM; on window end, ONE spoken digest ≤25s ("boss, while you were
in class: 3 things — …"), full list in app.
Per-type voice toggles (D35): `prefs.notif_toggles = {reminder:voice, habit:voice, brief:voice,
proactive:silent,…}` — the existing app toggle UI writes here; EVERY delivery reads it.

## VIII.3 Client behaviors
- Ringer-style squelch (D39): while ASTA is speaking a notification, volume/power keypress →
  immediate stop (local, no round-trip), auto-ack as "silenced" (distinct from "noted").
- Audio routing: if BT earbuds connected → force route to BT only; else speaker.
- Ambiguity (D49): "remind me at 7 to call amma" → if 7 could be AM/PM given now-time, ASTA asks
  in the same breath ("7 tonight or tomorrow morning, boss?") — never guesses.

## VIII.4 Offline local reminders (D41)
When a reminder is created, phone ALSO schedules a local `AlarmManager` mirror (next 48h only).
If WS+FCM unreachable at fire time, the phone speaks via **sherpa-onnx/Piper** on-device TTS
from the mirrored text and queues the ack for sync. Server reconciles by dedupe_key on reconnect.

## VIII.5 DoD (Phase 5)
Voice-created reminder fires as voice, acked by voice · airplane-mode reminder speaks locally ·
5-day school week: zero audible proactive speech 09:00–16:00, digest ≤25s at 16:00 · double-fire
impossible (kill server between WS speak and FCM, verify single logical delivery by dedupe log) ·
volume-press silences mid-sentence.

---

# PART IX — PROACTIVITY, REFLECTION, HABITS (Phase 6; D44–D48, D63)

## IX.1 Scheduler architecture (one beat, many jobs)
Single APScheduler instance; every job = idempotent function keyed by `(job_id, logical_date)`
with a `job_runs` Mongo log. The 03:00 self-test (R5) asserts yesterday's expected runs exist —
silent scheduler death is detected within a day, in the morning brief.
```
05:00 brief-prep · 05:30 alarm-support · hourly habit-engine tick · 20:30 daily recap ·
21:30 wake-time proposal · 22:00 Sun reflection · 23:00 extraction sweep (stragglers) ·
23:30 filler-pool regen · 23:50 quota report · 00:30 idea-graveyard · 01:00 nightly prediction ·
02:00 backups · 03:00 self-test · Sun 22:40 weekly export
```

## IX.2 Proactive engine (D44) — observe → propose → act
Signals table: deadline_risk (open_loops with due<48h & no progress events), contradiction
severity≥4 unacked, health (sleep<5h streak), stale idea, connection-match (graph: Person whose
expertise entity ∩ active project entities → "boss, Ravi knows Neo4j — worth a ping?").
Each signal → ONE proposal message (voice if allowed, else silent). Karthik ignores → asked once
"want me to drop the X thing?" → then dropped and logged (D-Q49). Justification string is stored
with every proactive contact — the weekly reflection audits whether proactivity was worth it.

## IX.3 Daily recap (20:30; prompts/daily_recap.md)
```
Write ASTA's evening recap for Karthik. ≤120 spoken words. Structure: (1) one-line day verdict,
(2) done vs planned (from Notion diff + habit log), (3) ONE honest miss with pattern context if
memory shows one ("third Tuesday in a row DSA lost to youtube"), (4) tomorrow's single most
important thing, (5) if a stale idea exists: the research/schedule/kill question. Register: {register}.
Honest, warm, zero flattery. Inputs: {notion_diff} {habits} {usage_summary} {stale_idea} {weights}
```
Delivered by voice (ladder rules apply) + one Notion block appended to a "Daily Log" page.

## IX.4 Sunday reflection (22:00; prompts/weekly_reflection.md — the blunt one)
Runs on Gemini Flash long-context with the WHOLE week (all insights + habit log + usage + Notion
diffs + last week's reflection for continuity):
```
You are ASTA writing Karthik's Sunday reflection. He explicitly wants true colors — no filtering,
no bluffing, no cruelty either. Output two artifacts:
A) SPOKEN (≤200 words): the week in one honest paragraph; stated vs behaved priorities with the
   biggest gap called out with numbers; one pattern he probably can't see; one genuine win; one
   concrete change for next week (small, specific).
B) NOTION PAGE (markdown): ## Verdict · ## Priorities: stated vs behaved (table) · ## Patterns
   (evidence-linked) · ## Wins · ## Misses & why (pattern, not blame) · ## Contradictions status ·
   ## Screen/usage report · ## Next week: 3 commitments (his words where possible)
Cite evidence by date. If the data shows a good week, SAY it plainly — honesty cuts both ways.
```
Then: Notion page created, Google Doc appended (V.11), spoken part delivered.

## IX.5 Habit engine (D48)
```
habits {_id, name, schedule, verify: health_workout|health_steps|notion_check|word,
        streak, escalation: 0 nag →1 guilt →2 negotiate →3 consequence, last_state_ts}
```
Hourly tick evaluates due habits. Verification: jogging = Health Connect workout OR >2500 steps
in a morning window; else ask ("did the jog happen, boss? honest answer"). Escalation copy comes
from prompt files per level; level 3 = honest reporting only ("logging this week as 2/5 jogs —
it'll be in Sunday's reflection"), NEVER punitive (D-Q114). Success → de-escalate one level +
streak celebration (register playful); broken streak → inspiration mode, never shame (D-Q121).
2AM intervention (D-Q115): usage event stream shows video app active past 01:45 → one gentle
live line via voice-if-earbuds/silent-otherwise ("boss. episode ends, phone sleeps, deal?") →
no repeat for 45min → logged for reflection.

## IX.6 Nightly prediction (D46, capped)
01:00: one router call — "given open loops, tomorrow's Notion plan, and priorities, what ≤2
things will Karthik likely need prepared?" → allowed actions: pre-run a research-lite (5 sources)
into a draft Notion page, or pre-pull docs for a blocked project. Hard cap 2 items, skipped
entirely if any provider ledger <30% headroom (R9 pays proactive compute last).

## IX.7 DoD (Phase 6)
14 straight days of recaps + 2 reflections delivered and logged · stated-vs-behaved table shows
real numbers · one stale idea surfaced and resolved through the loop · escalation ladder walked
up and down on a real habit · 2AM trigger fires in a controlled test · job_runs audit green daily.

---

# PART X — RESEARCH PARTNER v2 (Phase 7; D50–D54)

## X.1 Pipeline
```
voice convo captures HIS IDEA (2–3 clarifying Qs max: angle? deliverable? depth cue) →
query planner (router): 4–8 sub-queries →
source fetch: Serper (free tier) + arXiv API + direct docs fetch; RANKER: official/original first —
  domain allowlist boost (arxiv.org, *.github.io of the project, official docs domains, standards),
  aggregator/SEO penalty list; dedupe by canonical URL →
per-source distillation (map) → synthesis (reduce, evidence-linked) →
NOTION PAGE (4 sections, D50): # <topic> · ## HIS IDEA (his words, cleaned) · ## FINDINGS
  (claims with inline links) · ## COMBINED SOLUTION (his idea × findings — the merge is the
  value) · ## NEXT STEPS (checkboxes) · ## SOURCES (+ fetched PDFs as file blocks, D53) →
spoken recap ≤30s → memory: research node linked to topic entities (enables D51 "building on
your May deep-dive", surfaced whenever topic similarity >0.8)
```
No time cap (D50) but a progress heartbeat: filler-style updates every ~90s ("12 sources in,
boss, two of them disagree — untangling it").

## X.2 Follow-ups & project mode
"go deeper on section 2" → page block cursor stored per research page → extends FINDINGS with a
`### Deeper: <aspect>` block (D51/D-Q105). Project mode (D54): planner detects build-intent →
appends ## ARCHITECTURE (components, data flow, stack with free-tier constraints inherited from
this guide's philosophy) + ## IMPLEMENTATION PLAN (phased, testable) → offers dev-agent handoff:
"say the word and I'll start the base, boss" → one validation → PART XI takes over.

## X.3 Subscription (D53)
One default row in `subscriptions`: Sunday, topic = current top priority's research theme,
budget = 8 sources, output = append to a rolling "Weekly Radar" Notion page. Cancel/add by voice.

## X.4 DoD (Phase 7)
College test: voice-initiated research → correct 4-section page with ≥6 official sources, PDFs
attached, ≤30s recap · "go deeper" extends the SAME page · a related later topic triggers the
"building on" reference · heartbeat lines during a >3min run.

---

# PART XI — DEV AGENT (Phase 8; D55–D61, R8)

## XI.1 Concepts
Separation of powers: **server plans, laptop executes, jail contains.** The gateway is a dumb,
paranoid executor — all intelligence stays server-side where it's auditable. Assume the server
could one day be compromised: the gateway's job is to make that survivable (allowlist + jail +
HMAC + audit), which is why hardening precedes the first real task.

## XI.2 Gateway v2 (laptop; evolves gateway/openclaw_gateway.py)
Envelope:
```json
{"v":2, "id":"uuid", "ts": 1720000000, "nonce":"...", "cmd":"exec",
 "argv":["git","status"], "cwd":"~/asta-projects/projX", "timeout_s":600,
 "hmac":"HMAC_SHA256(secret, canonical_json_without_hmac)"}
```
Checks in order — fail closed, log everything:
1. HMAC valid (constant-time compare) · 2. `|now-ts| < 120s` and nonce unseen (sqlite nonce
cache, 24h TTL) — replay-proof · 3. `argv[0] ∈ ALLOWLIST = {git,python,python3,node,npm,npx,
pip,uv,ollama,docker(compose subcmds only),openclaw}` · 4. jail: `realpath(cwd)` startswith
`realpath(~/asta-projects)`; every path-like arg re-checked; reject `..`, absolute paths outside
jail, symlink escapes · 5. env scrubbed to a minimal PATH+HOME (no inherited keys — D60) ·
6. execute `shell=False` (keep), stream stdout/err, enforce timeout, kill process group on cancel.
Extras: `cmd:"kill_switch"` (terminates all children, locks gateway until manual restart);
append-only `audit.jsonl` (id, ts, argv, cwd, exit, duration, bytes-out); runs as user-level
service (Task Scheduler/NSSM on Windows), bound 127.0.0.1, reachable ONLY via **Tailscale**
(server→laptop `100.x.y.z`); Windows Firewall rule: port 8888 allow from tailscale interface only.
Secret provisioning: generate once on laptop, paste into server `.env` by hand — never over the wire.

## XI.3 Execution brain on the laptop
`ollama pull qwen2.5-coder:{7b|14b-q4}` (OPEN-3 decides; 8GB VRAM → 14b-q4 with partial offload
is usable, 7b is snappy). OpenClaw: Docker, version-pinned, ONLY `~/asta-projects` mounted, no
ClawHub skills, localhost bind, mDNS off, WS origin checks on — configured once, config committed
to a private `laptop-setup/` folder in the repo.

## XI.4 Orchestration (server; D55–D56, D59)
```
task = {goal, notion_plan_page, project_dir, caps:{wall:90m, loops:25, groq_calls:60}}
loop:
  plan/critique step → router("coding_brain")           # Groq kimi-k2: decompose, review output
  execute step        → gateway {argv | openclaw task}   # local Ollama does the typing
  milestone in {plan_done, scaffold_done, base_done} → notify ladder (Q93 pings + live log in app)
  stuck|ambiguous → state=waiting_boss, message Karthik, PAUSE (D-Q94)
  caps hit → summarize state honestly, stop (D59)
git protocol: init if new; branch asta/<task-id>; commit per milestone with generated messages;
final: push nowhere (local), report = branch name + diffstat + how-to-run + test results (ran,
not gated — D-Q96) + open questions.
```
Model split heuristic: architecture/review/tricky-file prompts → Groq; bulk generation/edits →
Ollama via OpenClaw. Rationale in the audit log per step (tunable later).

## XI.5 Shakedown (D61)
Before any real project, three canned tasks graduate the stack: (1) hello-FastAPI with 1 test,
(2) CLI scraper with README, (3) small React page. Pass = clean audit trail, caps respected,
kill switch verified mid-task, zero writes observed outside jail (run with a filesystem watcher
on $HOME during shakedown).

## XI.6 DoD (Phase 8)
One voice command → validated plan → base built in jail on a branch with honest report · HMAC-
tampered and replayed envelopes rejected+logged · `rm` and out-of-jail path rejected · kill switch
<2s · audit.jsonl reconstructs the entire session · laptop offline → task queues with a clear
"laptop's asleep, boss" message.

---

# PART XII — OFFLINE & PC CLIENT (Phase 9; D41, Q68/70)

## XII.1 Android offline brain
Components: **Vosk small-en** (~40MB) for offline STT of commands; intent grammar (not free chat):
capture / reminder / task-complete / query-cached; **sherpa-onnx TTS** (Piper voice) for offline
speech; SQLCipher `offline_queue` (exists — reuse) with idempotent batch sync:
`POST /sync {items:[{client_id, kind, payload, created_ts}]}` → server dedupes by client_id,
applies, returns per-item status. Conflict rule: server state wins, client edits become new events.
Offline chat is explicitly out of scope (v1 decision, kept): ASTA says (via Piper) "offline,
boss — captured it, I'll handle it when we're back."

## XII.2 PC client (tray app, Python)
pystray + sounddevice: wake word (IV.6) → Pipecat WS client to server → same voice loop, same
mic-window prefs, same notification speaks (so ASTA talks at the desk too, Q70/74). Config =
server URL (Tailscale name) + device token. Autostart via Task Scheduler. The PC client and the
gateway are separate processes — voice never gets exec powers.

## XII.3 DoD (Phase 9)
Airplane mode: 5 captures + 1 reminder → reminder speaks via Piper on time → reconnect → all 5
synced exactly once · PC: "hey asta" at the desk → full conversation → a due reminder speaks
through PC speakers when phone is elsewhere.

---

# PART XIII — OBSERVABILITY, BACKUP, DR (continuous; R5–R7)

## XIII.1 Health & self-test
`GET /health` → real checks with 2s timeouts: mongo ping, neo4j ping, redis ping, groq 1-token,
notion whoami, disk %, outbox backlog, scheduler last-beat. `{status: ok|degraded|down, deps:{...}}`
— no lying "ok". 03:00 self-test job runs `ops/verify/nightly.py` (subset of make verify against
prod: WS echo turn, memory write+recall roundtrip on a synthetic session, reminder schedule+cancel,
yesterday's job_runs audit) → failures = FCM alert by 03:05 + morning-brief line. Dead-man:
`curl $HEALTHCHECKS_URL` every 5 min from the beat loop; silence >10min → email.

## XIII.2 Backups & restore (R7)
02:00: `mongodump --archive | age -e -r <pubkey>` → rclone to Drive `asta-backups/` (keep 14
daily, 8 weekly) · Sundays: Aura backup export where available, plus a logical fallback that
ALWAYS works: replay-rebuild script `ops/rebuild_graph.py` (re-feeds all insights through
Graphiti — possible because Mongo is the source of truth, V.1). `ops/restore.sh` = provision box
(cloud-init/compose) → restore dump → rebuild graph → smoke verify. **Drill it once in Phase 6
week: measured target <2h, documented in ops/DR.md.**

## XIII.3 Retention
Raw audio deleted after transcription (keep 24h for STT debugging, then purge). Transcripts +
insights permanent (D-Q22). Logs 30 days. audit.jsonl (gateway) permanent.

---

# PART XIV — VERIFY & EVALS (grows every phase)

`make verify` (ops/verify/, runs in CI nightly against staging creds + via 03:00 self-test):
```
P0 boot: import app, /health ok            P1 voice: WS synthetic-turn roundtrip <3s, barge-in unit
P2 wake: golden feature-parity vector      P3 memory: write→extract→recall→correct→private (all asserted)
P4 morning: brief-gen from fixtures        P5 notify: schedule→ladder simulation→ack→dedupe assertions
P6 jobs: job_runs audit for logical-date   P7 research: fixture pipeline → 4 sections present
P8 gateway: hmac/replay/jail/allowlist unit suite (runs on laptop CI too)
P9 sync: idempotent batch replay twice → once applied
```
**Memory evals** (`tests/evals/memory.jsonl`, run weekly with persona evals): 20 Q→expected-
behavior pairs seeded from real usage ("what are my top priorities" must list current weights;
"when did I last talk about X" must cite a date; a corrected fact must answer NEW value). Judge
model scores; trend graphed in the app's health page. LLM systems rot silently — evals are how a
real system notices before you do.

---

# PART XV — THE 20 RULES (print this)

1. Mongo event log is sacred; everything else is rebuildable. 2. Outbox pattern for every fanout.
3. Prompts are versioned files, never inline strings. 4. One mic owner on Android. 5. Utterance-
based STT + reflex filler beats fake streaming. 6. Sentence-chunked TTS always; cache the phrases
you say daily. 7. Free tiers = quotas are weather: ledger, failover, shed. 8. Never sync-retry a
429 on the same provider. 9. Idempotency keys on: extraction, reminders, sync, jobs, episodes.
10. The alarm has zero remote dependencies. 11. Detect force-stop; don't pretend to survive it.
12. Every proactive contact stores its justification. 13. Nag ≤3, then genuinely drop it.
14. Honest failure lines beat silent retries ("my memory write failed, noted, retrying").
15. The gateway is paranoid and dumb; intelligence stays auditable on the server. 16. Jail +
allowlist + HMAC + audit BEFORE the first real dev task. 17. A feature without a verify line
doesn't exist. 18. Evals weekly or the persona/memory rots invisibly. 19. Deploy is git-pull-
compose; SSH edits are how prod diverged last time. 20. When in doubt, delete scope — the kernel
(alarm → brief → voice → capture → memory → reminders → research → dev agent) is ASTA; everything
else is decoration.

— end of guide —
