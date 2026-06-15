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
- [x] `backend/preferences/content_style_prefs.json` placeholder is intentional — Kartik confirmed (2026-06-14) it should fill in organically via the existing "remember this for my posts" voice-update path as the content feature gets used, rather than from a separate style file
- [x] `content` intent + chained flow (uses thread research if present; else offers research / raw topic)
- [x] Post/script generation per platform prefs; review (draft + question, phase-persisted); regenerate on feedback
- [x] Images: 2 variants via image_service on request
- [x] Final bundle logged to Notion Content DB (handoff to external posting pipeline)
- [x] "Remember this for my posts" updates preferences via voice-update path
- [x] Full §4 one-sitting flow passes on one thread
- [x] Commit: "Day3 research→content chain live"

## DAY 4 — VOICE + TEST UI
- [x] Voice routes research/content intents correctly; long outputs summarized for TTS
- [x] React UI: persistent session, interrupt questions UI, drafts + images render, TTS playback
- [x] Reminder fire delivered to open WS client (visible/audible)
- [x] Morning brief manually triggered through NEW supervisor (weather + tasks [+ news]) and speaks
- [x] Commit: "Day4 voice + cockpit solid"

## DAY 5 — MOBILE + PROOF
- [x] ASTA MOBILE submodule initialized, pointed at backend (ngrok auto-discover), bearer in config — `AstaNetworkClient`/`ASTAForegroundService` bearer + ngrok-discovered BASE_URL fixed; verified live via ngrok `/api/ngrok-url` + `/api/me` + `/api/chat`
- [x] Conversation works from phone (backend reachable + authed end-to-end via ngrok, gradle build green); reminder notifies on phone via `ProactiveListenerService` (WS → `asta_proactive` → notification), wired into `MainActivity` + manifest. On-device verification DONE: physical device connected, `ProactiveListenerService` WS confirmed authenticated (server.log `[WS] Client connected` + `session_start`), created a real 2-minute reminder via `/api/chat`, scheduler fired it at 23:31:00, and `dumpsys notification` on-device shows the resulting notification (channel `asta_reminder_channel`, importance=HIGH, text "Boss — mobile notification test — it's 23:31."). Re-verified post-restart (after all 5 DAY5 #4 fixes): fresh reminder fired at 00:20:00 IST exactly on schedule (server.log job removed + executed successfully), and `dumpsys notification` shows the resulting `asta_reminder_channel` notification's `mLastNotificationUpdateTimeMs` at 00:19:59.982 IST — within 20ms of the server fire, confirming the WS push pipeline survived all 5 restarts intact
- [x] ⚠️ partial — Memory proof: 3 themed conversations written to memory (Pinecone vectors 23→26, Mongo L4 confirmed); task-creation conversation produced a real Notion link (https://app.notion.com/p/MEDIUM-email-the-Solstice-deck-to-Priya-37e337e75d1781708157ed31d75537c2). Fixed a `classify_intent` routing bug so recall reaches `other_workflow`. Root-caused the ungrounded recall to 3 real bugs (not just Neo4j): `l3_vectors.py` crashed on list-type `topics` metadata (silently zeroing ALL searches), and `entity_extractor.py`/`memory_saga.py` had no Gemini fallback so a Groq 429 permanently replaced session summaries with "Extraction failed..." placeholders (this is what destroyed `mobile-proof-1/2/3`'s embeddings). All 3 fixed + routed through `llm_factory` (also fixed a dead `gemini-1.5-flash` model name there — Gemini fallback had never worked). A 5th, project-wide bug was also found+fixed: `session_manager`'s 5s/45s batch retry loop was perpetually re-running entity extraction (and burning a full Groq `generate` call) on permanently-`partial_sync` sessions, since Neo4j can never succeed while down — this is the likely root cause of the chronic ~99.9/100k Groq TPD exhaustion affecting the whole project, not just memory. Fixed via `graph_service.get_existing_nodes()` returning `None` on connection failure + `memory_saga` short-circuiting on that signal (no LLM call); verified post-restart (log shows "Neo4j unreachable - skipping entity extraction", zero Groq/Gemini calls). Verified end-to-end: post-restart, `MemorySaga` successfully extracted real entities via the new Gemini fallback for 2 sessions. A fresh "Project Aurora" recall demo to replace `mobile-proof-*` could NOT be completed: Groq `llama-3.3-70b-versatile` TPD (~99.9/100k) and Gemini `gemini-2.5-flash` daily free quota (20/day) were BOTH exhausted at the time of testing — the drain is now fixed (fix #5), so Groq should recover naturally; a retry should be left for later. See BLOCKED.md
- [x] Test rows archived (Notion row `37e337e7-5d17-8170-8157-ed31d75537c2` archived); `.env` confirmed never committed to git history (no key rotation needed); tag `v0.1-functional`
- [x] Commit + tag — `11e521f` (superproject) + `a2e9d44` (ASTA MOBILE submodule), tag `v0.1-functional`

## WEEK 2+ (parked)
- [ ] Deploy (Railway / DO droplet), domain + SSL
- [ ] Wire Kartik's external posting automation as a tool
- [ ] Morning brief polish (news prefs, nag loop tuning)
- [ ] Mobile showcase screens (workflow visualizer, architecture view)
- [ ] Habit tracking decision (fix KeyError or delete)
- [ ] Developer agent (its own month)
