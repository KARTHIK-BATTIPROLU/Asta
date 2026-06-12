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
- [ ] `research` intent routed in supervisor (supervisor-owned nodes so interrupt binds)
- [ ] Clarifying questions via interrupt (angle/depth), then Serper+scrape+arxiv research
- [ ] Notion Research DB page: summary / researched points / combined takeaways
- [ ] Research result held in thread state + saved to memory
- [ ] Acceptance conversation passes; Neo4j nodes + Pinecone vectors grew
- [ ] Commit: "Day2 research vertical live"

## DAY 3 — CONTENT CHAINED
- [ ] `backend/preferences/content_style_prefs.json` created from Kartik's style file
- [ ] `content` intent + chained flow (uses thread research if present; else offers research / raw topic)
- [ ] Post/script generation per platform prefs; interrupt for review; regenerate on feedback
- [ ] Images: 2 variants via image_service on request
- [ ] Final bundle logged to Notion Content DB (handoff to external posting pipeline)
- [ ] "Remember this for my posts" updates preferences via voice-update path
- [ ] Full §4 one-sitting flow passes on one thread
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
