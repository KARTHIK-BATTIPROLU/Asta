# BLOCKED — items needing Kartik's action

## 1. content_style_prefs.json is a PLACEHOLDER (Day 3, item 1)

**Item:** D3.1 requires `backend/preferences/content_style_prefs.json` built from
Kartik's real ChatGPT-derived style file. No such file was found anywhere in the
repo (only `linkedin_prefs.json` / `youtube_prefs.json` / `instagram_prefs.json`
existed, which are platform-specific, not the master style overlay).

**What was done:** Created `backend/preferences/content_style_prefs.json` as a
PLACEHOLDER following the schema the BLUEPRINT specifies (tone / structure / hooks /
hashtags / emoji / avoid / per_platform), seeded with reasonable first-principles
defaults consistent with the existing per-platform prefs files. It is marked
`"_placeholder": true` with a `"_note"` field. `content_manager.py` loads and merges
it with the platform-specific prefs file for every generation, and the
"remember this for my posts" voice-update path
(`preferences_service.update_from_voice("content_style", ...)`) writes directly into
this doc in Mongo (`preferences` collection, `type="content_style"`), so Kartik's
real preferences will naturally override the placeholder once he starts using it.

**What Kartik must do:** Either (a) say "remember this for my posts: ..." a few
times to organically build up `content_style_prefs` in Mongo, or (b) hand Claude
Code his real ChatGPT-derived style file and ask it to replace
`backend/preferences/content_style_prefs.json` with the real values (same schema).

## 2. Reminder delivery has no offline/push fallback (mobile)

**Item:** found during the consolidation pass while documenting the reminder
pipeline. `ASTA MOBILE/.../service/ProactiveListenerService.kt` delivers reminders
ONLY via a live WebSocket connection (`asta_proactive` messages) held open by a
foreground Android service, which then posts a local `NotificationCompat`
notification. Grep for `FCM|firebase|push|Notification` found no Firebase Cloud
Messaging code anywhere in the mobile app — there is no push channel at all.

**Impact:** if the phone is offline, the app/service has been killed by Android
(Doze / battery optimization / OS memory pressure), or the WS connection has
dropped for any reason, a reminder that fires server-side at its scheduled time
(`broadcast_message` to `/ws/conversation`) is simply LOST — no retry, no queued
delivery, nothing reaches the device. This was NOT hit during Day 5 testing only
because the foreground service + WS connection stayed alive across all 5 restarts
on the test device.

**What Kartik must do:** decide priority/scope —
1. **No action**: keep relying on the foreground WS service. Works reliably as long
   as the app stays running and the phone has connectivity (verified in Day 5).
2. **Add a real push fallback**: requires a Firebase project (Kartik-owned account
   action — create project, download `google-services.json` into
   `ASTA MOBILE/app/`, get a server key), backend changes to send an FCM push when
   no WS client is connected at fire-time, and an Android `FirebaseMessagingService`
   that can show a notification even when the app/service is fully killed. This is
   a real feature addition, not a quick fix — out of scope for this consolidation
   pass.

---

## Known limitations (informational — not blocking, no action needed from Kartik)

### LangGraph 1.1.3 — second `interrupt()` in a resumed node

If a supervisor node calls `interrupt()` a SECOND time during a RESUMED execution
(already resumed once via `Command(resume=...)`, then hits a new `interrupt()`
further down), the checkpoint ends up with `snap.interrupts` non-empty but
`snap.next == ()`. A THIRD `Command(resume=...)` then finds nothing resumable and
runs from an empty fresh state instead (confirmed via a standalone repro).

`content_workflow` avoids this with only ONE `interrupt()` total — the
review/regenerate step is a normal response + `content_state["phase"] =
"awaiting_review"` persisted on the thread, and `classify_intent` short-circuits
the next turn back to `content_workflow` based on that phase.

**Latent same-class risk:** `task_manager._handle_reschedule`
(`backend/app/workflows/task_manager.py:272-282`) has TWO sequential
`interrupt()` calls ("which task?" then "what time?"). If one message triggers
BOTH (ambiguous task name AND no new time given), the second interrupt may hit
this issue on the next reply. Not fixed — pre-existing Day 1 code, rare in
practice. If the task_manager regression test ever fails on a double-ambiguity
case, apply the same phase-persistence pattern used in `content_workflow`.
