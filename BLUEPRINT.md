# ASTA — MASTER BLUEPRINT
> **This file is the single source of truth.** Every Claude Code session must read this first.
> Owner: Kartik. Last updated: 2026-06-12.
> Companion file: `TODO.md` (checkbox progress). Update both as work ships.

---

## 1. WHAT ASTA IS

ASTA is Kartik's personal AI companion — a single consciousness accessible from
mobile, laptop, and (later) smartwatch. It is NOT a chatbot. It:

- **Remembers everything** — every conversation grows a knowledge graph (Neo4j)
  + vector memory (Pinecone). It never forgets projects, people, skills, promises.
- **Pushes Kartik** — proactive reminders that actually FIRE and notify
  ("you said you'd work on certificate-gen at 7pm — it's 7pm").
  Reminders are the #1 value of this project.
- **Researches like a co-pilot** — real-time web + arxiv + scraping → structured
  findings → Notion. Then iterates with Kartik to produce architectures and code.
- **Creates content in one sitting** — idea → research → post/script in Kartik's
  style (from preferences file) → images → output handed to the external posting
  pipeline (Buffer/social tools — a SEPARATE existing project; ASTA never posts
  directly to LinkedIn/Instagram/YouTube).
- **Speaks** — voice in/out (Deepgram), wake word on mobile, barge-in.

## 2. LOCKED DECISIONS (do not re-litigate)

| Decision | Choice |
|---|---|
| Orchestration | LangGraph. ONE supervisor: `backend/app/core/supervisor_graph.py`. The old `core/supervisor.py` must die. |
| Conversation model | **Approach B** — research and content creation are sub-flows INSIDE one conversation thread. Memory flows through: research → post generation → images, all on one `thread_id`. |
| Checkpointer | MongoDB (`asta_checkpoints`), same store locally and in Docker. `thread_id = session_id`, stable per conversation. |
| Multi-turn | `langgraph.types.interrupt()` + `Command(resume=...)`. Interrupts live in nodes owned by the supervisor graph. |
| Memory | ONE stack: top-level `memory/memory_engine.py` (L1 Redis → L2 Neo4j → L3 Pinecone → L4 Mongo). Embeddings: MiniLM-L6-v2, **384 dim**, single source `memory/embeddings.py`. |
| LLM | `core/llm_factory.py` ONLY. Groq primary (8b-instant classify/quick, 70b-versatile generate), Gemini flash fallback. Old `llm_router.py` must die. |
| Posting | ASTA outputs content (text + hashtags + images). Kartik's external automation (Buffer-style) handles approval/scheduling/publishing. NO direct platform APIs in ASTA. |
| Preferences | JSON files in `backend/preferences/` seeded into Mongo via `preferences_service`. Content style = `content_style_prefs.json`. ASTA may UPDATE preferences when told "remember this for my posts". |
| Developer agent | **DEFERRED.** Not this month. Do not build. |
| Habit graph / YouTube / Instagram autonomy | Defer beyond script generation. Fix-or-delete only when touched. |
| Deployment | Local + ngrok this week. Server (Railway / DO droplet) is Week 2. NOT Render free tier (cron dies on spin-down). |

## 3. ARCHITECTURE (target state, end of this build)

```
Mobile (Kotlin+Flutter, wake word, WS client, ngrok auto-discover)
Laptop (React test UI → WS)
        │  voice/text, stable session_id
        ▼
FastAPI  /api/chat  +  /ws/conversation (BOTH bearer-authed)
        ▼
SUPERVISOR GRAPH (checkpointed, Mongo)
  classify_intent ──► routine_workflow ──► task_manager (CRUD + interrupt)
        │                    └──► routine_graph (morning/night briefs)
        ├──► research_workflow ──► research_service (Serper/scrape/arxiv)
        │         └──► Notion Research DB + memory
        ├──► content_workflow (chained AFTER research on same thread)
        │         ├─ load content_style prefs
        │         ├─ generate post/script (70b)
        │         ├─ image_service (Gemini Imagen-3)
        │         └─ Notion Content DB → handed to external posting pipeline
        └──► other_workflow (chat + memory context)
        ▼
  save_session (EVERY turn) ──► memory_engine
        ├─ entities → Neo4j nodes/edges (Kartik → projects/skills/people)
        ├─ summary → Pinecone vector (384)
        └─ session → Mongo
SCHEDULER (APScheduler, same supervisor path)
  ├─ 05:30 morning brief   ├─ 22:30 night planning
  └─ per-task one-time reminders → fire → WS broadcast + (mobile notification)
```

## 4. THE TARGET CONVERSATIONS (acceptance examples)

**Reminder that fires:**
> K: "Tomorrow morning remind me to call Suresh about the community event"
> A: "Got it — what time tomorrow morning?" → K: "9am"
> A: writes Notion + schedules job. AT 9:00 the next day, ASTA pings over WS/mobile: "Boss — call Suresh about the community event."

**Research → content, one sitting, one thread:**
> K: "I got an idea — research how platforms like SocialPost connect to LinkedIn/Instagram/YouTube APIs, then make me a LinkedIn post about what I learned"
> A: researches (Serper+scrape+arxiv) → writes structured page to Notion Research DB → "Research done, here's the gist… now drafting your post" → loads `content_style_prefs` → drafts post + hashtags → "want images?" → generates 2 via Imagen → outputs final bundle → logs to Notion Content DB. Kartik feeds it to his posting automation.

**Memory recall, days later:**
> K: "What did I research about social posting platforms?"
> A: pulls the session via Neo4j cluster → Pinecone → answers with specifics + Notion link.

## 5. BUILD PLAN — 5 DAYS

### DAY 1 — SPINE INTEGRITY (make what exists trustworthy)
1. **session_id fix**: `/api/chat` must accept and ECHO a client `session_id`; frontend + WS already pass one — make the React test UI persist it (localStorage). No more `chat-{timestamp}` mints per request.
2. **One supervisor**: repoint the 05:30/22:30 cron callbacks to `run_supervisor_graph` (routine hint); delete `core/supervisor.py`; migrate the graphs off `llm_router.py` → `llm_factory`; delete `llm_router.py`.
3. **REMINDERS THAT FIRE** (the crown): in `task_manager._handle_create`, after the Notion write, parse the time → `scheduler_service.add_one_time_reminder(...)` → on fire: WS `broadcast_message` + mark in Notion. Add **startup reload** of pending future reminders from Notion (APScheduler store is not persisted). Test with a 2-minute-out reminder.
4. **WS auth**: re-enable bearer check on `/ws/conversation` (mobile + frontend send token).
5. Hygiene: one venv, one requirements.txt, commit.

### DAY 2 — RESEARCH WIRED (Approach B, step 1)
1. Add `research` routing edge in supervisor → new `research_workflow` node that adapts SupervisorState → research flow (reuse `research_graph` nodes/logic or call `research_service` directly inside supervisor-owned nodes so `interrupt()` binds).
2. Conversational probing uses interrupt (ASTA may ask 1–2 clarifying questions: angle? depth?), then researches, synthesizes, writes Notion Research DB page (3 sections: conversation summary / researched points / combined takeaways).
3. Research result is kept IN STATE on the thread (and in memory) so the content step can chain.
4. Acceptance: the "research SocialPost-like platforms" conversation works end-to-end, page lands in Notion, memory accumulates (Neo4j nodes + Pinecone vector grow).

### DAY 3 — CONTENT CHAINED (Approach B, step 2)
1. Create `backend/preferences/content_style_prefs.json` (Kartik supplies his ChatGPT-derived style file; agent defines schema: tone, structure, hooks, hashtags policy, emoji policy, per-platform variants).
2. Add `content` routing + chained flow: if research exists on the thread → use it; else offer to research first or take the topic raw. Generate post (LinkedIn) / script (YouTube/Instagram) per platform prefs → interrupt for review → regenerate on feedback → optional images via `image_service` (2 variants) → final bundle → Notion Content DB log.
3. "Remember this for my posts" → updates the preferences (preferences_service voice-update path).
4. Acceptance: full one-sitting flow from §4 works on one thread.

### DAY 4 — VOICE + TEST UI SOLID
1. WS voice path: confirm research/content intents route correctly from voice; chunked TTS responses for long outputs (summarize-for-voice, full text to Notion).
2. React test UI: persistent session, shows interrupts as questions, renders post drafts + images, plays TTS. This is the development cockpit.
3. Reminder firing → verify delivery over WS to an open client (and define the mobile push hook for Day 5).
4. Morning brief (05:30 path) manually triggered → runs through NEW supervisor → brief includes weather + tasks + (news if SERPER set) → speaks.

### DAY 5 — MOBILE + PROOF
1. Init/point ASTA MOBILE at the backend (ngrok auto-discovery already built); bearer token in app config; conversation + reminders notify on phone.
2. Memory proof: run 3 themed conversations, then a recall question — verify graph nodes/edges + vector counts grew and recall works.
3. Sweep: archive test rows, rotate any leaked keys, commit, tag `v0.1-functional`.

## 6. RULES FOR EVERY CLAUDE CODE SESSION
1. Read `BLUEPRINT.md` + `TODO.md` first. Work ONLY on the current TODO item unless told otherwise.
2. Smallest change that passes. Never refactor working spine code (supervisor_graph, task_manager, checkpointer, memory_engine) unless the task demands it.
3. Read real state (schemas, env, index dims) — never assume.
4. Imports: `from backend.app.*`; memory stays top-level `memory/`.
5. interrupts must live in supervisor-owned execution so `Command(resume=...)` binds to the thread.
6. Every feature must prove: works via /api/chat, survives restart (checkpoint), and writes memory.
7. After each task: update TODO checkboxes, print PASS/FAIL, clean up test data, commit with a clear message.
8. Never commit `.env`. Never print live secrets.

## 7. OUT OF SCOPE THIS WEEK
Developer agent · direct platform posting · habit autonomy · smartwatch ·
health sensors · 3D workflow visualizer (mobile showcase polish comes after
functional) · AWS/cloud deploy (Week 2) · multi-user anything.
