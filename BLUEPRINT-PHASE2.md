# ASTA — PHASE 2 BLUEPRINT
> **Single source of truth for Week 2 work.** Read this before every Claude Code session.
> Owner: Kartik. Companion file: `TODO-PHASE2.md` (checkbox progress). Update both as work ships.

---

## 1. WHERE ASTA IS NOW (Phase 1 — DONE)

ASTA is a personal AI companion that already:
- **Remembers everything** — Neo4j graph + Pinecone vectors (per-turn) + Mongo storage, single unified pipeline
- **Routes via a real checkpointed supervisor graph** (Mongo saver, interrupt/resume multi-turn)
- **Tracks routine** — create/list/complete/reschedule reminders, multi-turn clarification
- **Fires reminders** at scheduled times (currently WS broadcast only)
- **Researches** — Serper + arxiv + scraping + source filtering → Notion Research DB
- **Creates content** — research chains into post/script generation → images (Gemini Imagen) → Notion Content DB
- **Speaks** — Deepgram STT/TTS (voice works on web)
- **Recalls honestly** — refuses to fabricate; per-turn facts survive

**Current limitation it must fix:** every turn does full memory search → feels rigid/robotic/slow.
**Current gaps:** localhost only (not deployed), WS-only reminders (no phone push), placeholder content style, mobile voice not wired.

---

## 2. PHASE 2 VISION

Make ASTA **feel like a real assistant** and **actually reach the phone**:
- Fast, natural conversation — search memory only when it matters
- Posts that sound like Kartik (real preferences)
- Voice on the phone, not just laptop
- Reminders that reach the phone even when nothing's connected (FCM push)
- Always-on somewhere (deployed)

---

## 3. LOCKED DECISIONS (do not re-litigate)

| Decision | Choice |
|---|---|
| Dynamic memory routing | Intent-based. Recall/project questions fetch memory; casual chat + feedback skip the search. `save_session` runs ASYNC (never blocks the reply). |
| Content preferences | JSON `backend/preferences/content_style_prefs.json`. Placeholder NOW; Kartik supplies real data later. Voice-updatable ("remember this for my posts"). |
| Reminders — immediate | On fire, persist status to Notion instantly (visible even with no client connected). |
| Reminders — push | FCM (Firebase Cloud Messaging) for offline delivery. Bonus this phase. |
| Mobile voice | Wire audio streaming on the existing Flutter+Kotlin app over the EXISTING WS. Reuse Deepgram STT/TTS. No new vendor, no new endpoint. |
| Deployment | **Render free tier**, Docker web service (`render.yaml`). Kartik runs an external pinger (every 5 min) to keep the instance warm so the APScheduler-based reminders keep running; no Postgres/Redis add-ons — checkpointer falls back to MongoDB, L1 cache fails open. Accepted tradeoff over Railway/DO for $0 cost. |
| Firebase setup | Firebase CLI from Claude Code; `service-account.json` downloaded by Kartik; backend wires the Admin SDK send. |
| Human-in-loop work | Done LAST, never blocking: Firebase console clicks, content style file, mobile build, server/DNS. Placeholders keep everything running until then. |

---

## 4. ARCHITECTURE (target end-state)

```
PHASE 1 (works): Supervisor Graph (Mongo-checkpointed)
   → task_manager + research + content + chat, memory_engine save/fetch

PHASE 2 ADDS:
  Dynamic memory routing (in supervisor, after classify_intent)
    ├─ recall question      → fetch memory (Neo4j + Pinecone)
    ├─ project-context q     → fetch relevant project memory
    ├─ casual chat           → SKIP search, respond fast + warm
    └─ feedback/clarify      → thread context only, no search
    save_session → ASYNC, fire-and-forget (response returns immediately)

  Content preferences
    └─ load content_style_prefs.json each content turn → inject into prompt
    └─ "remember this for my posts" → preferences_service updates the JSON

  Mobile + voice
    └─ app: wake word → record → stream audio frames over existing WS
    └─ backend: Deepgram STT → supervisor → Deepgram TTS → audio back to phone
    └─ phone: plays response audio

  FCM push (bonus)
    └─ reminder fires → Firebase Admin SDK send → phone notification → tap opens app
    └─ app registers device token on launch; backend stores it

  Deployment
    └─ Railway or DO droplet runs the existing Docker Compose, always-on
```

---

## 5. TARGET CONVERSATIONS (acceptance)

**Dynamic routing:**
> K: "hey how's it going" → A (NO search, instant): "Hey! Doing great — what's up?"
> K: "what did I research about cert generators?" → A (searches, ~200ms): grounded answer + Notion link

**Content with real prefs:**
> K: "research SaaS platforms for my friend" → A researches → "Make a LinkedIn post?" → K: "yeah" → A loads content_style_prefs → post in Kartik's voice → "want images?"

**Mobile voice:**
> K (phone, wake word) "hey Jarvis" → records → "remind me to call Suresh 9am tomorrow" → A (audio) "Set for 9am tomorrow" → phone notification

**Reminder persistence:**
> reminder set 7pm → at 7pm Notion row status = fired (instant), and (bonus) FCM push on phone

---

## 6. BUILD PLAN — 4 AREAS (parallel-ready, no rigid days)

### AREA 1 — Dynamic Memory Routing  (the rigidness fix; highest user-facing value)
- Add a `should_search_memory` step after classify_intent (keyword + LLM signal)
- chat path fetches memory ONLY when recall/project; else pure warm chat
- `save_session` made async/non-blocking
- Tune heuristics so casual feels instant, recall stays grounded

### AREA 2 — Content Preferences  (0.5 day once file exists)
- Placeholder `content_style_prefs.json` already wired into every generation
- Replace with Kartik's real style later; voice-update path optional
- Posts use tone/structure/hooks/hashtags/emoji/avoid rules

### AREA 3 — Mobile + Voice
- App: audio capture → stream frames over existing WS
- Backend: route audio → STT → supervisor → TTS → phone playback
- Verify end-to-end on device/emulator

### AREA 4 — Deployment
- Choose Railway or DO droplet
- Deploy existing Docker Compose; set prod env (one checkpointer store, no localhost)
- Confirm reachable from phone (ngrok auto-discovery or real domain)

### BONUS — FCM Push (Week-2 if time)
- Firebase CLI creates project; enable FCM; download service-account.json
- Backend: Admin SDK send wired INTO reminder firing (alongside Notion persist)
- App: register device token, receive push, show notification

---

## 7. RULES (same spirit as Phase 1)

1. Read BLUEPRINT-PHASE2.md + TODO-PHASE2.md first, every session. Work the topmost unchecked item.
2. Smallest change that passes. NEVER refactor the live spine (supervisor_graph, task_manager, checkpointer, memory_engine) beyond what the task needs.
3. Read real state — schemas, env, index dims, versions. Never assume.
4. Imports `from backend.app.*`; memory stays top-level `memory/`.
5. Dynamic routing lives in the supervisor (always active), not bolted onto interrupt.
6. `save_session` MUST be async — the reply returns before memory writes finish.
7. Mobile audio rides the EXISTING WS — no new endpoint.
8. Every feature: PASS via `/api/chat` first, then WS/mobile; survive a restart; write memory.
9. After each item: tick TODO-PHASE2.md, print PASS/FAIL, clean up test data, commit clearly.
10. Never commit `.env` or `service-account.json`. Never print live secrets.

---

## 8. HUMAN-IN-LOOP WORK (do LAST — not blocking; placeholders keep things running)

| Task | Needed before | Kartik does |
|---|---|---|
| Real content style file | Area 2 "sounds like me" | Extract JSON from year-long ChatGPT thread |
| Firebase project + enable FCM | Bonus (push) | CLI auth + console clicks |
| Download service-account.json | Bonus (push) | Firebase console → file into backend secrets |
| Choose deploy target | Area 4 | Railway or DigitalOcean |
| Mobile build + on-device test | After Area 3 | `flutter build apk` + install + test voice |
| Domain + SSL (if DO) | After Area 4 | Buy domain, point DNS, certbot |

---

## 9. FALLBACK / PARTIAL RULES (mark, never silently skip)

If an item fails after 3 distinct fix attempts, or is blocked by a human-in-loop dependency:
- Log it in `BLOCKED-PHASE2.md`: item, exact error, what was tried, what Kartik must do.
- Mark the TODO item **⚠️ PARTIAL** — state precisely what works vs what's blocked.
- If nothing downstream depends on it → continue. If it does → build as far as possible, mark downstream ⚠️ PARTIAL, note the dependency.
- Placeholders are acceptable interim state: e.g. dummy `content_style_prefs.json` (posts still generate), local checkpointer if deploy store not chosen yet, ngrok if no domain yet. Everything must still RUN.

---

## 10. OUT OF SCOPE (Phase 2)

Developer agent · habit autonomy · YouTube/Instagram full automation · smartwatch · health sensors · 3D workflow visualizer · multi-user · custom wake-word training.

---

## 11. DEFINITION OF DONE (Phase 2)

- ✅ Conversations feel natural (dynamic routing live; casual = instant, recall = grounded)
- ✅ Content pipeline uses prefs (placeholder OR real file — both must work)
- ✅ Voice works on the phone end-to-end
- ✅ ASTA is always-on somewhere (deployed)
- ✅ Reminders persist to Notion the instant they fire
- ⚠️ FCM push complete OR clearly logged as blocked (Week-2)
- ✅ All tests pass, tree clean, zero Phase-1 regressions
