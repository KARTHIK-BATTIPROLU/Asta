# ASTA BLUEPRINT v2 — Decision Lock & Zero-Budget Architecture
> Built from Karthik's 131 questionnaire answers + repo audit + web research (July 2026).
> Supersedes v1 wherever they conflict. Every "take optimal decision" delegation is resolved here.
> Rule of this document: nothing is a suggestion. Everything is a decision unless marked OPEN.

---

# 0. THE PRIME CONSTRAINT: ₹0 / MONTH

Karthik's answer to Q53 rewrites the stack: **no money will ever be spent on ASTA.**
This is good. It kills vendor sprawl, forces consolidation, and makes ASTA survivable long-term
(a system that costs money dies the month you're broke; a ₹0 system runs forever).

## What dies, what replaces it

| v1 component | Problem | v2 replacement (free forever) |
|---|---|---|
| Anthropic API for insights/reflection | Paid | **Groq free tier** (llama-3.3-70b / kimi-k2) + **Gemini AI Studio free tier** as second provider |
| Deepgram STT | Paid after credits; misunderstands Karthik (Q61) | **Groq-hosted Whisper large-v3-turbo** — free tier, strong on Indian-accented English + Telugu code-switching, supports prompt biasing ("ASTA", "Karthik", tech vocab) |
| Deepgram TTS (MP3 batch) | Paid; batch = slow | **Kokoro-82M** self-hosted (open weights, real-time on CPU) for English; **edge-tts** (free MS neural voices, has Telugu te-IN voices) for Telugu segments + fallback; **Piper** on-device Android for offline speech |
| Pinecone | Whole vendor for one user's vectors | **Delete.** Vectors move to **MongoDB Atlas M0 vector search** (free) |
| Hand-rolled Neo4j L2 schema | Months of solo work to reach mediocre | **Graphiti (Apache 2.0)** running on **Neo4j Aura Free** — temporal facts with validity windows, contradiction-friendly (old fact closed, not deleted), configured with Groq as extraction LLM + local sentence-transformers embeddings |
| Custom ws_transport.py realtime loop | Where all the Sev-1 bugs live | **Pipecat** (open source, v1.0, vendor-agnostic) — barge-in, Silero VAD + SmartTurn semantic turn detection, interruption logic solved |
| openWakeWord "Hey Jarvis" prebuilt | Wrong name, high false triggers | **livekit-wakeword custom "Hey ASTA / ASTA" model** — ~100x fewer false positives than openWakeWord, exports ONNX/TFLite drop-in compatible with the existing Android openWakeWord runtime |
| EC2 (if billing) | Money | **Oracle Cloud Always Free ARM** (4 OCPU / 24 GB RAM, free forever) — comfortably runs FastAPI + Redis + Kokoro + embeddings. If current EC2 is inside 12-month free tier, keep until it expires, then migrate. **OPEN-1: confirm EC2 billing status.** |
| Google Calendar | Karthik: "no fkn calendar" (Q120) | **Notion is the only schedule/task source of truth.** calendar_tool.py → attic |
| Telegram alert channel | Q129: in-app only | FCM + in-app; **healthchecks.io free dead-man switch → email** for "backend is down" |

## LLM provider strategy (replaces "2–3 Groq accounts")
Multiple free accounts on one provider violates Groq's terms and gets keys banned mid-day —
a reliability bug, not a hack. The robust version of the same idea:

**One account per provider, rotate across providers.** Router with per-provider rate-limit
counters and automatic failover:
1. **Groq** — primary. Realtime convo (llama-3.3-70b-versatile), STT (whisper-large-v3-turbo), coding brain (kimi-k2 / best free coder available).
2. **Google AI Studio (Gemini Flash)** — second. Also does free embeddings + long-context jobs (weekly reflection over a week of sessions).
3. **Cerebras / Mistral La Plateforme / OpenRouter free models** — third and fourth.
4. **Ollama on laptop** (via Tailscale) — last-resort overflow + all dev-agent execution.

Router lives in `llm_factory.py` (already exists — extend it): tracks tokens/min and req/day
per provider, degrades gracefully, logs every failover. Tool use via MCP-style registry so new
tools plug into any provider (Q31).

---

# 1. DECISION LOCK

Every question answered "optimal/best choice" is resolved below. Veto anything within 48h;
after that these are frozen and specs get written against them.

## 1.1 Persona (Q3–12, 43, 59, 60, 72)
- **D1.** System prompt defines ASTA as: nerdy, funny, warm — a genuine buddy. Calls Karthik **"boss"** by default, **"Karthik"** in serious/motivational moments.
- **D2.** Mood-adaptive: a lightweight per-turn signal (sentiment of Karthik's words + time of day + recent wellbeing data) selects one of 4 registers: playful / focused / serious / concerned. Jokes disabled in serious+concerned.
- **D3.** Short answers by default; short paragraph max unless asked.
- **D4.** Decision-nagging: when Karthik states a choice ASTA's memory flags as conflicting (priorities, past failures, health), ASTA pushes back up to **3 times**, then records disagreement and drops it (Q6, Q49).
- **D5.** **Never flattery. Honest and concerned** — hard rule in prompt, tested in evals (D-EVAL below).
- **D6.** Reflections are unfiltered: "show me true colors" (Q43). Daily recap gentle-honest; Sunday brief blunt.
- **D7.** Language: English default; Telugu/Tenglish when Karthik uses it (Whisper transcribes it; edge-tts te-IN speaks it).
- **D8.** Wake acknowledgment: rotating dynamic greetings ("yes boss, wassup", "go ahead boss", time-aware variants). Never the same twice in a row.

## 1.2 The Filler/Engagement Layer — Karthik's #1 UX demand (Q7, 30, 52, 63)
- **D9.** Two-stage response architecture in Pipecat:
  - **Reflex stage (≤400 ms):** an intent classifier on the transcript predicts operation cost. If long (memory dig, research, dev task), ASTA immediately speaks a **contextual filler** — "wait boss, that one's buried deep, digging it up", a topical fact, or a quip. Filler pool is pre-generated nightly by Groq from recent conversation topics (50 lines, cached), so it's dynamic but costs zero latency.
  - **Main stage:** real answer streams in and takes over.
- **D10.** Filler never fires for fast turns (<1.5s expected). No filler twice in a row with the same template family.

## 1.3 Memory / Second Brain (Q13–38)
- **D11.** **Storage consolidation:** MongoDB Atlas M0 = source-of-truth event log + vector index (episodic insights). Neo4j Aura Free + **Graphiti** = temporal semantic graph (entities, priorities, rules, contradictions with validity windows). Redis = local container on the server box, hot cache only, loss-tolerant. Pinecone deleted.
- **D12.** Ingestion sources at launch: voice/chat sessions, Notion (full workspace read + sync), phone usage (Digital Wellbeing), Health Connect (sleep/steps), nightly voice journal, "ASTA, note:" quick capture. Wave 2: Gmail (read-only), GitHub events, YouTube history (Q123).
- **D13.** What gets remembered: **hybrid** — auto-extraction on session end (one Groq call: what did this session reveal — decisions, priorities, emotional state, contradictions) + explicit "remember this" tags which get 2x retrieval weight (Q14).
- **D14.** **Quick capture:** lock-screen tile / wake word / share sheet → <5s to durable local queue → synced. Captures land in an "Inbox" node; the nightly job classifies them (idea / task / note / research-seed).
- **D15.** **Idea graveyard fix (Q16):** every captured idea auto-becomes a Notion "Idea" entry with status. If untouched 7 days, ASTA raises it once in a daily recap ("that caching idea from last Tuesday — research it, schedule it, or kill it?"). Ideas can be killed guilt-free; killed ≠ deleted.
- **D16.** Memory is **permanent** (Q22); no decay for now, but retrieval ranks behavioral-relevance > recency > similarity (from v1, kept).
- **D17.** **Memory editing (Q23):** "that's wrong, actually X" → Graphiti closes the old fact's validity window, opens the new one; correction propagates because retrieval only surfaces currently-valid facts.
- **D18.** **Private mode (Q25):** "ASTA, off the record" → session flagged; no extraction, no vectors, no graph writes; raw log kept in Mongo with `private:true` (retrievable only by explicit request), or "off the record, no trace" → not persisted at all.
- **D19.** **Memory Explorer UI (Q24):** phase 10 — searchable timeline + graph view + "what do you believe about me" page showing priority weights and rules, each with an edit/dispute button.
- **D20.** Insight extraction runs **fully automatic** after a one-time architecture walkthrough + approval from Karthik at launch (Q32).
- **D21.** Seeded priorities (Q34 — ASTA asks in first onboarding convo, presenting these as starting options): DSA, jogging/health, ASTA-the-project, community, content, sleep, college. Weights drift on a **weeks** timescale (Q35). Both stated-vs-behaved scores tracked and shown (Q36).
- **D22.** **Weekly export (Q38):** every Sunday after reflection, append a digest section to a single running Google Doc ("ASTA — Weekly Memory Log") via Google Docs API (free), plus a full JSON dump of the week's new memories to Google Drive (15 GB free) as backup.

## 1.4 Voice Pipeline (Q51–64)
- **D23.** **Migrate the realtime loop to Pipecat.** ws_transport.py's custom loop is retired after parity. Pipecat pipeline: SmallWebRTC/WS transport → Silero VAD → Groq Whisper STT (with bias prompt) → router/LLM → sentence-chunked Kokoro TTS → out. Barge-in and interruptions come from the framework.
- **D24.** STT accent fix (Q61): Whisper large-v3-turbo + `initial_prompt` containing "ASTA, Karthik, Notion, Neo4j, DSA, LeetCode…" (maintained vocab list); measured target: name recognized ≥95% of attempts.
- **D25.** Latency budget: first audio (filler or answer) ≤ 1.2 s p50; Karthik accepts long tails because the filler layer covers them (Q52).
- **D26.** Mic stays open **5 s** after ASTA finishes, for wake-word-free follow-ups; **app setting: 5 / 10 / never** (Q56), read by both phone and PC clients from one server-side preferences doc.
- **D27.** Noise: jogging/road use (Q57) → Pipecat noise suppression on, wake word threshold profile "outdoor" auto-selected when Health Connect reports an active workout.
- **D28.** Whisper-quiet mode after 22:30 or on command; auto-restores (Q59).
- **D29.** Mishears → ask again, don't guess (Q64).

## 1.5 Wake Word (Q65–74)
- **D30.** Train custom **"Hey ASTA" + "ASTA"** models with livekit-wakeword (synthetic TTS data incl. Indian-English voices + 50 real samples Karthik records — **OPEN-2**). Export TFLite/ONNX → existing Android openWakeWord runtime unchanged; also run on PC client.
- **D31.** Bias toward **fewer false accepts** (Q66 says the phrase is key; Q73 says class-time triggers are unacceptable): threshold tuned so FPPH < 0.2, accept saying it twice occasionally.
- **D32.** 24/7 foreground service, ≤10% battery/day target (Q67–68). If measured drain >10%, auto-downshift to charging-only + hardware trigger and tell Karthik.
- **D33.** Hardware triggers (Q71): volume-up long-press 3 s (phone + wired), earbud tap — all open the same listen session.
- **D34.** Speaker verification (Q69): phase 11 nice-to-have (resemblyzer on-device); not a launch blocker since threat model is "only me in the room" mostly.

## 1.6 Notifications as Voice — the Jarvis layer (Q75–84)
- **D35.** **Every ASTA-originated notification speaks**: reminders, briefs, deadlines, proactive nudges — full-duplex Jarvis style (Q75). Per-notification-type voice on/off toggles in app (the existing toggle system, wired properly).
- **D36.** Delivery ladder: WS live voice → if unacked in 60 s, FCM push (with **"OK / Noted" action buttons**, Q77) → re-speak every **5 min** until acked → after 3 re-pings, park it in "next engagement" queue and daily recap.
- **D37.** Voice ack: saying "ok / noted / got it" within the listen window acks it (Q77).
- **D38.** Interruption etiquette (Q76): if Karthik is mid-conversation with ASTA, the notification waits for turn end, then: "boss, quick one — [reminder]".
- **D39.** Routing (Q81): earbuds connected → earbuds only (private). Speaker → volume/power button instantly silences the current utterance, like a ringing call.
- **D40.** Tone adapts to content: urgent deadline = clipped and serious; habit nudge = playful (Q82).
- **D41.** Offline: time-critical reminders scheduled ALSO as local Android alarms with **Piper on-device TTS** so ASTA still speaks with zero backend (Q83).
- **D42.** **Auto-silent weekdays 09:00–16:00** (Q47, 73): proactive voice muted, everything queues; on unmute, spoken digest ≤ 25 s (Q80), full list in app.
- **D43.** No reading other apps' notifications (Q79). Dropped from scope.

## 1.7 Proactivity & Reflection (Q39–50, 111–122)
- **D44.** Proactive contacts: **unlimited when justified** (Q39), justified = deadline risk, contradiction threshold, health signal, idea-graveyard item, or connection-match ("Ravi in your network knows X", Q45). Outside silent window only. Observe → propose → act on yes (Q48); after asking once about an ignored thing, drop it (Q49).
- **D45.** **Daily recap** (evening, voice + one Notion block): today vs priorities, wins, one honest miss. **Sunday 22:00 weekly reflection** (voice + Notion page + Google Doc append): patterns, stated-vs-behaved priorities, pros/cons, blunt (Q41–43).
- **D46.** Idle-time compute, bounded: one nightly prediction pass — "what will Karthik likely need tomorrow" (class topics, blocked project, stale idea) — pre-researches at most **2** items/night on free tier (research shows moderate budgets are the sweet spot; Q44).
- **D47.** Morning flow (Q2, 111–117): alarm (dynamic time: default 05:30, ASTA may propose ±45 min from sleep debt/Notion schedule, Karthik confirms the night before) → awake-verification conversation (2–3 dynamic questions referencing yesterday — cheating-resistant because they require recall, not button presses) → **5-min brief**: weather → tech/AI news (2–3 items) → yesterday's incomplete → today's commitments from Notion → one focus suggestion. Length adapts (Q117).
- **D48.** Habits (Q113–115, 120–122): Notion is task SoT with offline internal queue that syncs back (Q118). On top: a **daily habit tracker** (jog, DSA, sleep-by-time, journal) with dynamic reminders. Jogging verified via Health Connect steps/workout when available, else Karthik's word. Escalation stays **nag → guilt → negotiate → consequence(honest reporting only)** — no app blocking (Q114). 2 AM anime → live gentle intervention (Q115). Streaks tracked and celebrated; broken streak → inspiration not shame (Q121). Weekend profile derived from actual sleep time (Q122).
- **D49.** Reminder ambiguity (AM/PM, vague dates): **ask** (Q119).

## 1.8 Research Partner (Q101–110)
- **D50.** No time cap (Q101). Flow: capture Karthik's raw idea/angle first (voice convo) → search official/primary sources only — docs, arxiv, standards, original blogs; ranking penalizes SEO aggregators (Q102) → Notion page in the v1 4-section layout: **HIS IDEA / FINDINGS / COMBINED SOLUTION / NEXT STEPS** (Q103, fixing the current hardcoded generic sections) → ≤30 s spoken recap.
- **D51.** Research is memory-aware: retrieves past related research and says so ("building on your May deep-dive", Q104). Follow-ups extend the same page ("go deeper on section 2", Q105).
- **D52.** Passing "I wonder if…" mentions → logged as research-seed, surfaced in daily recap; auto-research only if it matches a top-3 priority (Q106).
- **D53.** Papers: fetch PDFs, section summaries, files + links attached under the research page (Q107). Scheduled subscriptions: one default — "weekly: what's new in [top priority topic]" — Sunday, cheap, cancelable (Q108). Citation style: every claim linked inline (Q109 "best" = verifiable).
- **D54.** **Project mode** (Q2, 85): if the topic is a build, the same flow continues into ARCHITECTURE + IMPLEMENTATION PLAN sections, then hands off to the dev agent (below) after Karthik's one validation.

## 1.9 Dev Agent (Q85–100)
- **D55.** Roles: **ASTA (server, Groq brain) = architect/manager. Laptop = hands.** OpenClaw runs on the ASUS TUF A16 with **Ollama (qwen2.5-coder — 14B Q4 if the GPU has 8 GB VRAM, else 7B; OPEN-3: confirm GPU model)** for local execution, but planning, task decomposition, and code review prompts come from ASTA via Groq's best free coder (kimi-k2 / llama-3.3-70b). This matches Q88 ("ASTA manages, probably Groq") and Q95 (dev agent backed by local Ollama as the tool).
- **D56.** Flow (Q85, 91–96): research+architecture Notion file → **one** voice/notification validation from Karthik → ASTA drives OpenClaw to build the **base** of the project autonomously → progress: milestone pings at plan/scaffold/base-done + live log in app (Q93) → stuck/ambiguous = message Karthik and wait (Q94) → done report; **no test-gate before reporting** (Q96) but agent runs whatever tests it wrote and reports results honestly.
- **D57.** **Blast radius (Q86, 97):** hard jail to `~/asta-projects/` (one folder, many sub-projects). Never ASTA's own repos. Package installs allowed inside per-project venv/node_modules only. Deletes only inside the jail. Git init every project; every agent session = one branch + commits → rollback is `git reset` (Q99). Non-git actions logged for manual undo.
- **D58.** **Gateway v2 hardening (Q87, 90–91):** the current 119-line gateway gets: bind 127.0.0.1 (keep) + **auth token + HMAC-signed command envelopes + command allowlist (openclaw, git, python, node, npm, pip within jail) + append-only audit log + kill-switch command + workspace-jail path validation**. Laptop ⇄ server over **Tailscale** (free personal tier) — port 8888 is never exposed to the internet. OpenClaw itself: pinned version, Docker-sandboxed with only the jail mounted, no ClawHub third-party skills (7% leak credentials per Snyk), config per its hardening guide (localhost bind, no mDNS, WS origin checks).
- **D59.** Budget/caps (Q95): local model = free, so caps are wall-clock (90 min/task) + iteration limit (25 agent loops) + Groq-call ceiling per task; on cap, stop, summarize state, ask.
- **D60.** Secrets for built projects: added by Karthik after base completes (Q98) — agent scaffolds `.env.example`, never real keys.
- **D61.** First projects (Q100): ASTA picks 3 from Karthik's idea inbox, smallest-first, as the dev agent's shakedown cruise.

## 1.10 Data & Wellbeing (Q123–131)
- **D62.** Integrations, final list: **Notion, Health Connect, Gmail (read-only, wave 2), YouTube history (wave 2), GitHub (wave 2).** Nothing else. Calendar/Spotify/Telegram/WhatsApp/banking: out.
- **D63.** Usage data (Q126): ASTA learns patterns silently; intervenes live only for the defined vices (2 AM anime, doomscroll >45 min in a study block); weekly screen report inside the Sunday reflection.
- **D64.** GitHub commits (wave 2) feed the "behaved priorities" signal (Q127). Location: app-granted, used for context (left campus, on jog route), never stored raw beyond 24 h (Q128).

---

# 2. TARGET ARCHITECTURE (v2)

```
┌──────────────── PHONE (Android) ────────────────┐
│ Wake word: custom "Hey ASTA" (openWakeWord rt)  │
│ Hardware triggers: vol-up 3s / earbud tap       │
│ Pipecat client (WebRTC/WS) ── mic/speaker       │
│ Local fallback: Piper TTS + Vosk-small STT      │
│   + SQLCipher queue + local alarms (alarm NEVER │
│   depends on backend)                           │
│ FCM receiver ─ ack buttons ─ per-type toggles   │
└───────────────┬─────────────────────────────────┘
                │ WSS (token+device bound)
┌───────────────▼──────── SERVER (Oracle Always-Free ARM or free-tier EC2) ─┐
│ FastAPI + Pipecat pipeline (VAD→STT→LLM→TTS, barge-in)                    │
│ Reflex layer: intent cost classifier → filler speech ≤400ms               │
│ LLM Router: Groq → Gemini → Cerebras/Mistral → laptop Ollama              │
│ STT: Groq Whisper large-v3-turbo (bias prompt) │ TTS: Kokoro (CPU) +      │
│                                                  edge-tts (Telugu/fallbk) │
│ MEMORY: Mongo Atlas M0 (event log + vectors) ── Graphiti on Neo4j Aura    │
│         Redis (local container, hot cache)                                │
│ Schedulers: morning brief · daily recap · Sun 22:00 reflection ·          │
│   nightly extraction+prediction(≤2) · idea-graveyard · habit engine       │
│ Notion sync (SoT for tasks) · Google Docs/Drive weekly export             │
│ healthchecks.io dead-man ping                                             │
└───────────────┬───────────────────────────────────────────────────────────┘
                │ Tailscale (private mesh — port 8888 never public)
┌───────────────▼──── LAPTOP (ASUS TUF A16) ──────┐
│ PC client: wake word + voice (same Pipecat)     │
│ Gateway v2: HMAC + allowlist + audit + jail     │
│ OpenClaw (Docker, pinned, no ClawHub skills)    │
│   └── Ollama qwen2.5-coder ── ~/asta-projects/  │
└─────────────────────────────────────────────────┘
```

---

# 3. THE REAL-SYSTEM DOCTRINE
*(what separates ASTA from a fancy project — enforced, not aspirational)*

**R1. The backend must boot before anything else matters.** Current state: it doesn't
(missing `get_api_key` import, `routine_engine.py` IndentationError, `ctx.ctx` crash loops,
`stt_stream` NameError). These die first, in Phase 0, before any v2 feature.

**R2. CI or it will happen again.** GitHub Action on every push: `python -m compileall`,
`import backend.app.main`, `pytest`. Two of the current Sev-1 bugs are literally a syntax
error and a missing import — a 2-minute pipeline makes that class of failure extinct.
Pre-commit hook locally with the same checks.

**R3. Delete the halo.** Move to an `attic` branch (recoverable, out of the build):
`instagram_graph.py, linkedin_graph.py, youtube_graph.py, youtube_engine.py, content_engine.py,
content_manager.py, sheets_service.py, image_service.py, calendar_tool.py, weather via sheets,
render.yaml, process_turn_temp.py, memory_saga.py (finish the retirement main.py still imports!),
duplicate deploy/nginx.conf, start_asta.bat`. Also: `.gitignore` the committed `graphify-out/`
cache junk. One start script. One nginx conf. The kernel is: **alarm → brief → voice loop →
capture → memory → reminders → research → dev agent.** Everything else waits.

**R4. Verification is a build artifact.** `make verify` runs the golden path end-to-end
against real infra: boot → WS voice round-trip → session end → memory written (Mongo+Graphiti
assertions) → retrieval returns it → reminder fires → notification acked. A feature without a
line in `make verify` doesn't exist. Brutal tests from v1 stay (3 consecutive mornings after
force-stop+reboot for the alarm).

**R5. ASTA monitors ASTA.** `/health` reports per-dependency truth (Mongo, Neo4j, Redis, Groq,
Notion). Nightly self-test at 03:00 runs `make verify` remotely; failures arrive as an FCM push
by 03:05 and in the morning brief ("boss, my memory write failed overnight, running degraded").
Dead-man switch: server pings healthchecks.io every 5 min; silence → email.

**R6. Degradation ladders everywhere, no all-or-nothing.**
Voice: Pipecat streaming → REST batch → text push. STT: Groq Whisper → Gemini audio → on-device
Vosk. TTS: Kokoro → edge-tts → Piper local. LLM: router chain. Memory read fails → conversation
continues + honest note. Backend dead → phone still: alarms, local reminders with Piper voice,
capture queue. **The 5:30 alarm has zero remote dependencies. Ever.**

**R7. Data can't die.** Nightly `mongodump` → Google Drive (encrypted archive). Weekly Neo4j
dump. Weekly human-readable digest → the Google Doc (D22). Server rebuild = one script:
`docker compose up` + restore + `.env` from Karthik's password manager. Target: dead server →
fully restored in under 2 hours.

**R8. Security is Phase 0, not Phase 9.** In order: (1) rotate every leaked key TODAY —
Groq, Mongo, Neo4j, Notion, Serper, OpenWeather, Gemini, bearer token (Deepgram/Pinecone/
Anthropic get rotated then cancelled); (2) make the Asta repo private (ASTA_APP already is);
(3) purge hardcoded ngrok fallbacks in `AstaNetworkClient.kt` / `ConfigManager.java`;
(4) commit the uncommitted EC2 patches; (5) wss + real domain or Tailscale-only access;
(6) Gateway v2 hardening (D58) before the dev agent ever runs.

**R9. Cost is a tested invariant.** A daily job sums provider usage vs free-tier quotas; if any
provider crosses 80% of its daily quota, the router sheds load (shorter contexts, local models)
and tells Karthik in the recap. ₹0 is enforced by code, not hope.

**R10. One change stream.** Everything through git. No SSH-edited files on the server (that's
how the uncommitted-EC2-patches mess happened). Deploy = `git pull && docker compose up -d`.

---

# 4. PHASE PLAN v2

| # | Phase | Contents | Pass condition (brutal test) |
|---|---|---|---|
| 0 | **Stabilize & Secure** (now) | R1 bug kill-list, R2 CI, R3 attic purge, R8 keys/private repo/ngrok purge, R10 git discipline, OPEN-1 hosting decision | `make verify` boots backend green; CI red on injected syntax error; old keys revoked & confirmed dead |
| 1 | **Voice core on Pipecat** | Pipecat pipeline, Groq Whisper + bias prompt, Kokoro/edge-tts, barge-in, reflex/filler layer (D9), mic-window setting | 20-turn outdoor convo: barge-in works 10/10; "ASTA" recognized ≥19/20; filler plays on every slow op |
| 2 | **Wake word "Hey ASTA"** | Train livekit-wakeword model (OPEN-2 samples), Android+PC deploy, thresholds, hardware triggers, battery profiling | 48h real use: 0 class-time false fires, ≤2 missed activations/day, ≤10% battery |
| 3 | **Memory v2** | Graphiti+Neo4j, Mongo vectors (Pinecone off), session-end extraction, quick capture, private mode, memory correction, Notion ingest | Say a fact Mon; three days later ASTA uses it unprompted. Correct it; old fact never resurfaces. "Off the record" leaves no trace |
| 4 | **Morning system** | Local-only alarm, awake-verification convo, 5-min brief from Notion+weather+news, dynamic wake time proposal | 3 consecutive mornings after force-stop + reboot: alarm→convo→brief complete |
| 5 | **Jarvis notifications** | D35–D43 full ladder, voice acks, per-type toggles, silent window 9–16 weekdays, offline Piper reminders, unmute digest | Reminder set by voice fires by voice, acked by voice; airplane-mode reminder still speaks; nothing speaks in class for a week |
| 6 | **Recaps, reflection, habits** | Daily recap, Sunday blunt reflection, Google Doc export, habit tracker + escalation ladder, idea-graveyard loop, 2AM intervention | 2 full weeks: every recap/reflection delivered; one stale idea surfaced and resolved; Doc has 2 appended digests |
| 7 | **Research partner v2** | 4-section layout fix, memory-aware research, follow-up extension, PDF fetch, priority subscription | Voice-initiated research in college → correct 4-section Notion page + ≤30s recap + working "go deeper" |
| 8 | **Dev agent** | Gateway v2 hardening, Tailscale, OpenClaw+Ollama sandbox, D55–D61 flow, shakedown on 3 small projects | One voice command → validated plan → base project built in jail, branch+commits, honest report; audit log complete; kill switch verified |
| 9 | **Offline & PC client** | Vosk intent + Piper + queue sync on phone; PC wake word + voice client | Airplane mode: capture 5 items + 1 reminder → reminder speaks locally, all 5 sync on reconnect |
| 10 | **Memory Explorer & settings UI** | D19 UI, all app settings (mic window, notification toggles, silent windows), weekly-report view | Karthik disputes one belief in UI; behavior changes in next conversation |

Workflow unchanged from v1: plan in chat (specs from this doc), build with Claude Code
(free via your existing access — if none, the dev-agent stack itself: Groq + open tools),
never mixed. One phase in flight at a time; a phase is done only when its brutal test passes.

---

# 5. OPEN ITEMS — the only things Karthik must do

- **OPEN-1:** Is the current EC2 instance billing money? (Check AWS console → Billing.) If yes → Phase 0 includes migration to Oracle Always-Free ARM. If genuinely free for now → migrate when the free year ends.
- **OPEN-2:** Record ~50 short clips saying "Hey ASTA" / "ASTA" (quiet room, walking, with fan noise) — raises the custom wake model from good to excellent for your voice.
- **OPEN-3:** Which GPU is in the TUF A16 (RTX 4050/4060? VRAM?) → decides qwen2.5-coder 7B vs 14B.
- **OPEN-4:** Rotate the leaked keys and flip the Asta repo private — today, before any coding.
- **OPEN-5:** 48-hour veto window on any D-decision above; silence = frozen.
