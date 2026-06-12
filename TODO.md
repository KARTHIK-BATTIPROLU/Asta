# ASTA — TODO (companion to BLUEPRINT.md)
> Check items off as they ship. Claude Code: read BLUEPRINT.md first, work the
> topmost unchecked item, update this file, commit.

## ✅ ALREADY DONE (foundation)
- [x] Supervisor as real checkpointed StateGraph (Mongo saver, interrupt/resume)
- [x] Conversational task manager: create (multi-turn clarify) / list / complete (fuzzy) / reschedule
- [x] Notion Routine DB read/write verified live
- [x] Memory stack unified on memory_engine; save_session every turn; embeddings 384 single-source
- [x] Pinecone index `asta-memory-v2` dim-matched; Neo4j/Mongo/Redis/Groq/Notion all live
- [x] llm_factory: Groq primary + Gemini fallback
- [x] WS voice path: Deepgram STT/TTS, turn-state, barge-in
- [x] Resume-across-restart proven on stable thread_id
- [x] Root cleanup: ~49 throwaway scripts/docs deleted; old engines retired

## DAY 1 — SPINE INTEGRITY
- [x] `/api/chat` accepts + echoes client `session_id` (no per-request minting); React UI persists it
- [x] Cron callbacks (05:30 / 22:30) repointed to `run_supervisor_graph`; `core/supervisor.py` deleted
- [x] All graphs migrated `llm_router` → `llm_factory`; `llm_router.py` deleted
- [x] Reminders FIRE: create → `add_one_time_reminder` → at time: WS broadcast + Notion status
- [x] Startup reload of pending future reminders from Notion
- [x] 2-minute-out reminder test passes end-to-end
- [x] WS `/ws/conversation` bearer auth re-enabled (frontend + mobile send token)
- [x] One venv, one requirements.txt; hardcoded OpenWeather key moved to .env
- [x] Commit: "Day1 spine: one supervisor, firing reminders, ws auth"

## DAY 2 — RESEARCH WIRED
- [x] `research` intent routed in supervisor (supervisor-owned nodes so interrupt binds)
- [x] Clarifying questions via interrupt (angle/depth), then Serper+scrape+arxiv research
- [x] Notion Research DB page: summary / researched points / combined takeaways
- [x] Research result held in thread state + saved to memory
- [x] ⚠️ partial — Acceptance conversation passes; Pinecone vectors grew (4→5). Neo4j unverifiable: Aura instance `c706f89b` is a dead hostname (NXDOMAIN), see BLOCKED.md
- [x] Commit: "Day2 research vertical live"

## DAY 3 — CONTENT CHAINED
- [x] ⚠️ partial — `backend/preferences/content_style_prefs.json` created as PLACEHOLDER (Kartik's real style file not found in repo); see BLOCKED.md
- [x] `content` intent + chained flow (uses thread research if present; else offers research / raw topic)
- [x] Post/script generation per platform prefs; review (draft + question, phase-persisted); regenerate on feedback
- [x] Images: 2 variants via image_service on request
- [x] Final bundle logged to Notion Content DB (handoff to external posting pipeline)
- [x] "Remember this for my posts" updates preferences via voice-update path
- [x] Full §4 one-sitting flow passes on one thread
- [ ] Commit: "Day3 research→content chain live"

## DAY 4 — VOICE + TEST UI
- [ ] Voice routes research/content intents correctly; long outputs summarized for TTS
- [ ] React UI: persistent session, interrupt questions UI, drafts + images render, TTS playback
- [ ] Reminder fire delivered to open WS client (visible/audible)
- [ ] Morning brief manually triggered through NEW supervisor (weather + tasks [+ news]) and speaks
- [ ] Commit: "Day4 voice + cockpit solid"

## DAY 5 — MOBILE + PROOF
- [ ] ASTA MOBILE submodule initialized, pointed at backend (ngrok auto-discover), bearer in config
- [ ] Conversation works from phone; reminder notifies on phone
- [ ] Memory proof: 3 themed conversations → recall question answers with specifics + Notion link
- [ ] Test rows archived; any exposed keys rotated; tag `v0.1-functional`
- [ ] Commit + tag

## WEEK 2+ (parked)
- [ ] Deploy (Railway / DO droplet), domain + SSL
- [ ] Wire Kartik's external posting automation as a tool
- [ ] Morning brief polish (news prefs, nag loop tuning)
- [ ] Mobile showcase screens (workflow visualizer, architecture view)
- [ ] Habit tracking decision (fix KeyError or delete)
- [ ] Developer agent (its own month)
