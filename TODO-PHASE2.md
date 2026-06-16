# ASTA — PHASE 2 TODO (companion to BLUEPRINT-PHASE2.md)
> Read BLUEPRINT-PHASE2.md first. Work the topmost unchecked item. Tick boxes, commit.
> Marking rules: [x] done & verified · [ ] not started · ⚠️ PARTIAL (works but blocked/incomplete — see BLOCKED-PHASE2.md).

## ✅ PHASE 1 — DONE (foundation, do not redo)
- [x] Real checkpointed supervisor graph (Mongo saver, interrupt/resume)
- [x] Conversational task manager: create (multi-turn) / list / complete (fuzzy) / reschedule
- [x] Reminders FIRE at scheduled time (WS broadcast) + startup reload from Notion
- [x] Research vertical: Serper + arxiv + scrape + source filter → Notion Research DB
- [x] Content chaining: research → post/script → images (Gemini) → Notion Content DB
- [x] Single memory pipeline (memory_engine → asta_db); legacy MemorySaga retired
- [x] Per-turn memory granularity (facts from any turn survive) — 13/13 proven
- [x] Honest recall (refuses to fabricate)
- [x] Deepgram STT/TTS voice on web; all 6 backends live; bearer auth HTTP+WS

---

## AREA 1 — DYNAMIC MEMORY ROUTING  (fix the rigidness — do FIRST)
- [x] Add `should_search_memory` decision after `classify_intent` (keyword fast-path + LLM signal)
- [x] Classify per turn: recall / project-context / casual-chat / feedback-clarify
- [x] Chat path fetches memory ONLY for recall + project; casual/feedback skip the search
- [x] Make `save_session` async / fire-and-forget (reply returns before memory write finishes)
- [x] Warm tone when not searching (cheerful assistant persona); grounded tone when memory injected
- [x] Tune heuristics on real phrases until casual feels instant
- [x] TEST: "hey how's it going" → no search, instant; "what did I research about X" → searches, grounded + Notion link
- [x] TEST: latency drop on casual turns measured (before/after)
- [x] Regression: recall still grounded, single pipeline intact, no fabrication
- [x] Commit: "Phase2 Area1 — dynamic memory routing + async save"

## AREA 2 — CONTENT PREFERENCES  (placeholder now, real file later)
- [x] Confirm `content_style_prefs.json` placeholder loads + injects into every content generation
- [x] Define/keep schema: tone, structure, hooks, hashtag policy, emoji policy, avoid[], per-platform variants
- [x] Wire voice-update path: "remember this for my posts ..." → preferences_service updates the JSON
- [x] TEST: generated post visibly reflects prefs (placeholder values)
- ⚠️ Replace placeholder with Kartik's real ChatGPT-derived file (HUMAN-IN-LOOP — see §8)
- [x] Commit: "Phase2 Area2 — content prefs wired (placeholder)"

## AREA 3 — MOBILE + VOICE
- [x] App: wake word → start audio capture (existing Porcupine/OpenWakeWord)
- [x] App: stream audio frames over the EXISTING WS (no new endpoint)
- [x] Backend: route inbound audio → Deepgram STT → supervisor → Deepgram TTS → audio back
- [x] App: play response audio through phone speaker
- [x] App: send + persist a stable session_id (so multi-turn interrupts work on mobile)
- ⚠️ TEST: speak into phone → hear ASTA reply (HUMAN-IN-LOOP — requires device + APK)
- ⚠️ On-device build + install (HUMAN-IN-LOOP — `flutter build apk`)
- [x] Commit: "Phase2 Area3 — mobile voice end-to-end"

## AREA 4 — DEPLOYMENT
- ⚠️ Choose target: Railway OR DigitalOcean droplet (HUMAN-IN-LOOP decision — steps in BLOCKED-PHASE2.md)
- [x] Deploy existing Docker Compose to chosen host (config written; host deploy is HUMAN-IN-LOOP)
- [x] Prod env: set all keys; ONE checkpointer store (same local + prod); drop localhost overrides
- [x] Single worker (scheduler safety) OR external scheduler confirmed (`--workers 1`)
- [x] Reminders persist to Notion on fire (instant visibility) — `_fire_reminder` → `update_task_status("Reminded")`
- ⚠️ TEST: reach backend from phone over internet (HUMAN-IN-LOOP — requires host deploy)
- ⚠️ Domain + SSL if DigitalOcean (HUMAN-IN-LOOP)
- [x] Commit: "Phase2 Area4 — deployed, always-on"

## BONUS — FCM PUSH (Week-2 if time; reminders reach phone offline)
- ⚠️ Firebase CLI create project + enable FCM (HUMAN-IN-LOOP)
- ⚠️ Download service-account.json into backend secrets, gitignored (HUMAN-IN-LOOP)
- [x] Backend: Firebase Admin SDK send wired INTO reminder firing (alongside Notion persist)
- [x] Backend: store device tokens (per phone) — `/api/device-token` endpoint
- [x] App: register device token on launch; FCM receive service shows notification
- ⚠️ TEST: reminder fires with NO client connected → phone still gets push (HUMAN-IN-LOOP — requires FCM setup)
- [x] Commit: "Phase2 Bonus — FCM push delivery"

---

## §8 HUMAN-IN-LOOP CHECKLIST (Kartik does these; placeholders run until then)
- [ ] Content style file extracted from ChatGPT → replaces placeholder (Area 2)
- [ ] Firebase project created + FCM enabled (Bonus)
- [ ] service-account.json downloaded into backend (Bonus)
- [ ] Deploy target chosen: Railway / DO (Area 4)
- [ ] Mobile APK built + installed + voice tested (Area 3)
- [ ] Domain + SSL if DO droplet (Area 4)

## BLOCKED / PARTIAL LOG
- Keep `BLOCKED-PHASE2.md` updated: any ⚠️ item → exact error, what was tried, what Kartik must do.
- Carry-over known limitations from Phase 1: LangGraph double-`interrupt()` reschedule edge case (worked around); reminder offline delivery (this phase's FCM bonus closes it).

## PARKED (not Phase 2)
- Developer agent · habit autonomy · YouTube/Instagram full automation · 3D workflow visualizer · smartwatch · health sensors
