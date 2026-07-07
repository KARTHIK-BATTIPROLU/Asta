# ASTA — IMPLEMENTATION PLAN (to Optimal Jarvis)
> Ordered by your stated priorities: (1) proper AWS backend → (2) two-way voice incl. in-app → (3) morning brief → (4) reminders with AM/PM clarity → (5) memory/pattern/preference learning → (6) voice-first notifications → (7) glassmorphism chat UI.
> Each phase has a hard **Verify** gate — nothing counts as done until demonstrated on the physical phone against EC2.
> Companion file: `ASTA_WHAT_WE_HAVE.md` (current state).

---

## PHASE 0 — LOCK IN THE AWS BACKEND (½ day) 🔴 do first, everything depends on it

The backend works *right now* but the fixes live only on the EC2 disk, uncommitted.

1. **Persist server patches**: on EC2, commit `main.py`, `ws_transport.py`, `token_auth.py`, `settings_routes.py` (+ new `dependencies.py`, `deploy/neo4j_keepalive.py`) to the repo; pull/sync into the local working copy so laptop and server never diverge again.
2. **Fix the degraded items** (all small):
   - `pip install summa` + `python -m spacy download en_core_web_sm` in the venv → restores entity extraction and kills the SagaRetryWorker startup failure
   - CacheService datetime bug: serialize with `default=str` (or isoformat converter) in its `json.dumps` — kills ~60 errors per boot and makes session cache actually write
   - L1.5 prefetch kwargs: change the call at `memory_orchestrator.py:60` to match `set_speculative_data(key, value, ttl)` — the months-dead prefetch comes alive
3. **systemd hygiene**: `sudo systemctl daemon-reload` (unit file changed on disk); add `Restart=on-failure` with `StartLimitBurst` so a future crash-loop alerts instead of burning 8k restarts silently.
4. **Deferred but scheduled**: Elastic IP + domain + Caddy/Certbot HTTPS (moves WS to `wss://`, removes plaintext token). Not a blocker for functionality; is a blocker for calling it "proper" long-term.

**Verify:** `git status` clean on EC2 · reboot EC2 → service healthy with zero startup errors in journal → phone reconnects without touching the app.

---

## PHASE 1 — TWO-WAY VOICE, WAKE WORD **and** IN-APP (1–2 days) 🔴 flagship

### 1a. Finish wake word (one known edit)
- Apply the missing mel transform in `OpenWakeWordEngine.kt::extractMelspectrogram`: each mel value → `x / 10 + 2` (matches openWakeWord's official `melspec_transform`). Raw-int16 input fix is already applied.
- Rebuild → say "Hey Jarvis" → confidence must spike from ~1e-6 to >0.5. Tune threshold (start 0.5) and the 5 s cooldown.
- On detection `WakeWordService` already starts `ASTAForegroundService` — pause `WakeWordService`'s mic while a voice session is active (two AudioRecords on one mic = failure), resume on `audio_end`.

### 1b. Verify the full voice round-trip (wake-word path)
- "Hey Jarvis" → beep → speak "what time is it?" → watch server logs: STT transcript → supervisor → TTS frames → phone plays audio at 24 kHz.
- Fix whatever breaks in `turn_end`/VAD timing (the 8 s hard cap and 1.5 s silence window likely need tuning against real Deepgram latency).

### 1c. Enable in-app voice (mic button)
- Replace the "Voice mode disabled" toast in `MainActivity` with push-to-talk: tap mic → start `ASTAForegroundService` (same WS/audio path as wake word — **reuse, don't build a second pipeline**); tap again → force `turn_end`.
- Show live state in the chat UI (Listening… / Thinking… / Speaking) from the service's broadcast intents (`com.asta.MESSAGE_FROM_SERVICE` already exists).
- Transcripts and replies also append into the chat list so voice and text share one conversation view.

**Verify:** both entry points — across-the-room "Hey Jarvis" and in-app mic tap — produce a spoken answer, 5 turns in a row, app backgrounded included.

---

## PHASE 2 — MORNING BRIEF END-TO-END (1 day + 3 mornings of proof)

1. Dry-run first: `adb shell am start` the `WakeUpActivity` directly, and trigger `morning_alarm` on the backend manually — confirm the phone receives wake-up speech audio and plays it on the ALARM stream.
2. Brief content wiring: weather from device location (lat/lon already sent by `WakeUpActivity` when permission granted — request `ACCESS_COARSE_LOCATION` at first launch since it's currently denied), AI news via news tool, yesterday's incomplete tasks + today's schedule from Notion.
3. Snooze negotiation + awake-verification conversation over the same WS session (backend workflows exist — exercise and debug them).
4. Schedule a real 5:30 AM run.

**Verify (the brutal test):** force-stop app, reboot phone at night → alarm still fires at 5:30 with voice brief. Three consecutive mornings.

---

## PHASE 3 — REMINDERS WITH AM/PM CLARITY + RELIABLE DELIVERY (1 day)

1. **AM/PM disambiguation (backend `task_manager.py`)**: when extracted time has no meridiem and both interpretations are plausible (e.g. "remind me at 7"), raise the existing `interrupt()` clarification: *"7 AM or 7 PM, boss?"* Heuristics before asking: 24h times, "tonight/morning/evening" qualifiers, and past-time rollover (7 AM already gone → assume PM but *say so*).
2. Echo back the resolved absolute time in the confirmation ("Set for **7:00 PM today**") in both chat and voice.
3. Delivery hardening: reminder fires → WS `asta_proactive` **with `audio_base64`** (works now server-side) + FCM fallback when WS is down; `ProactiveListenerService` must dedupe so you don't get both.

**Verify:** set "remind me at 7" → ASTA asks AM/PM → answer → reminder fires at the right time as notification **and** voice (Phase 4 dependency for voice part), with app killed.

---

## PHASE 4 — EVERY NOTIFICATION SPEAKS (½–1 day) — "talking to me"

1. `ProactiveListenerService.onMessage`: when `asta_proactive` carries `audio_base64`, decode → MediaPlayer playback (notification/assistant usage attributes), **honoring silent mode** (skip audio, keep notification).
2. FCM push path: data-message includes the text; on receipt, if silent-mode off and WS wasn't already playing it, synthesize locally is NOT available — instead have FCM tap-through open the app which requests `/api/speak` replay. (Primary path stays WS audio; FCM is the visual fallback.)
3. Escalation levels: `escalation_level >= 2` plays on ALARM stream (already coded in `ASTAForegroundService.playMp3Response` — reuse the logic in the listener service).

**Verify:** trigger a reminder and a proactive nag with the app backgrounded → phone *speaks* them; toggle silent mode → text-only.

---

## PHASE 5 — MEMORY: FROM "CONNECTED" TO "LEARNING" (2 days)

Storage works (see state report §6). This phase turns on the learning loops:

1. **Bug fixes** (some land in Phase 0): prefetch kwargs, CacheService datetime, spaCy model. Then: migrate the last `graph_service` call sites to `l2_graph.py` and retire it — one Neo4j schema.
2. **Unblock pattern inputs on the phone**: guided permission flow (one screen, once): Usage Access, Health Connect steps+sleep, notifications, mic, location. `DailyMetricsWorker` then actually posts screen-time/steps/sleep every 30 min.
3. **Nightly pattern aggregation (backend)**: 10:30 PM job computes avg_sleep, wake time drift, productive hours, app-usage patterns → writes as properties on the Neo4j User node → injected into the supervisor's system context so ASTA *references them unprompted* ("you slept 5 hours, boss").
4. **Preference extraction loop**: after each session, a cheap-LLM pass extracts stated preferences ("I hate mornings", "call research tasks 'deep work'") → L2 graph as `User→PREFERS→X` edges → retrieved via existing entity-spotting into context.

**Verify:** mention project X today → fresh session tomorrow recalls it (already ✅); after 3 days of metrics, ASTA references your sleep/screen-time without being told; a stated preference from Monday shapes a Wednesday reply.

---

## PHASE 6 — GLASSMORPHISM CHAT UI (1–2 days, parallel-safe)

Redesign `activity_main.xml` + `ChatAdapter` (keep all logic, restyle only):
- Dark gradient backdrop; frosted-glass cards — translucent surfaces (#1AFFFFFF), 1 px white-alpha border, 24 dp radius, `RenderEffect.createBlurEffect` on Android 12+ (your Edge 50 Pro supports it), tint-only fallback below
- Message bubbles: user = subtle accent glass, ASTA = neutral glass; timestamp + delivery state
- **Voice state bar**: animated waveform/pulse strip showing Listening / Thinking / Speaking, driven by the service broadcasts from Phase 1c
- Mic FAB with pulse animation while a voice session is live; silent-mode switch restyled as a glass pill
- Status chip (Online / Offline-queueing) replacing the plain green/red dot

**Verify:** side-by-side screenshot review with you; jank test while a voice session streams.

---

## SEQUENCE & EFFORT SUMMARY

| Phase | What | Effort | Blocks |
|---|---|---|---|
| 0 | Backend persisted + degraded items fixed | ½ day | everything |
| 1 | Wake word fix + full 2-way voice + in-app mic | 1–2 days | 2, 3, 4 |
| 2 | Morning brief proven (3 mornings) | 1 day + proof window | — |
| 3 | AM/PM reminders + delivery | 1 day | 4 (voice part) |
| 4 | All notifications spoken | ½–1 day | — |
| 5 | Memory learning loops + metrics permissions | 2 days | — |
| 6 | Glassmorphism UI | 1–2 days | none (parallel) |

**~7–9 working days to the full checklist.** First action when we resume: the one-line mel transform (`x/10 + 2`) in `OpenWakeWordEngine.kt` — it was mid-edit when interrupted, and it unblocks the entire voice track.

## NOT IN SCOPE (per ASTA_CONTEXT.md guardrails)
LinkedIn/YouTube content, community automation, developer agent, PC fallback, watch, meeting auto-detect, weekly reviews — Phase 2+ of the product, not this plan.
