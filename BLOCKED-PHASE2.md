# BLOCKED — Phase 2 items needing Kartik's action

---

## 1. Content style file is a PLACEHOLDER (Area 2)

**Item:** `backend/preferences/content_style_prefs.json` exists and is wired into every
content generation, but its values are first-principles defaults, not Kartik's real voice.

**What works now:** All content turns load the placeholder, generate posts in the described
tone/structure, and the "remember this for my posts" voice-update path writes into Mongo.

**What Kartik must do:**
Option A — Say "remember this for my posts: ..." a few times while chatting; prefs accumulate
naturally in Mongo's `preferences` collection (type="content_style") and override the JSON.

Option B — Extract style from the ChatGPT thread and hand Claude Code the file. Replace the
contents of `backend/preferences/content_style_prefs.json` keeping the same JSON schema
(tone / structure / hooks / hashtags / emoji / avoid / per_platform).

---

## 2. Firebase project not created yet (FCM Bonus)

**Item:** No Firebase project exists; FCM send code is in place but will log a skip message
until `service-account.json` is present.

**What Kartik must do (in order):**

```
1. Go to https://console.firebase.google.com/ → "Add project" → name it "asta-push"
2. In the project dashboard → Project settings → Service accounts
   → "Generate new private key" → save the JSON file
3. Rename it service-account.json
4. Place it at: backend/secrets/service-account.json  (gitignored)
5. In the same project console → Build → Cloud Messaging → verify it is enabled
6. For Android: Project settings → General → "Add app" → Android
   → package name: com.example.asta
   → download google-services.json
   → place at: ASTA MOBILE/app/google-services.json
7. In ASTA MOBILE/app/build.gradle add:
     apply plugin: 'com.google.gms.google-services'
   and in dependencies:
     implementation 'com.google.firebase:firebase-messaging:23.4.0'
8. In ASTA MOBILE/build.gradle (project level) add:
     classpath 'com.google.gms:google-services:4.4.1'
9. Rebuild the APK.
```

---

## 3. Deploy target not chosen yet (Area 4)

**Decision:** Railway (managed, faster) OR DigitalOcean droplet (full control, cheaper
long-term). Choose ONE; step-by-steps for both are below.

---

### Option A — Railway (recommended for first deploy, ~$5/mo)

```
1. Install Railway CLI:  npm i -g @railway/cli
2. railway login
3. In the ASTA repo root:
     railway init          # creates project
     railway link          # links to the project
4. Add Postgres plugin inside Railway dashboard (or CLI):
     railway add --plugin postgresql
   Note the DATABASE_URL Railway sets automatically.
5. Add Redis plugin:
     railway add --plugin redis
   Note the REDIS_URL Railway sets automatically.
6. Set environment variables (copy from deploy/prod.env.example, fill real values):
     railway variables set ASTA_API_BEARER_TOKEN=...
     railway variables set GROQ_API_KEY=...
     railway variables set GEMINI_API_KEY=...
     railway variables set MONGO_URI=...
     ... (all keys from prod.env.example)
   POSTGRES_URL and REDIS_URL will be injected automatically by Railway plugins.
7. Add a railway.toml (or use the Dockerfile):
     [build]
     builder = "dockerfile"
     dockerfilePath = "backend/Dockerfile"
     [deploy]
     startCommand = "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --workers 1"
8. railway up          # builds and deploys
9. railway domain      # get the public URL (e.g. asta-xxx.up.railway.app)
10. Update the phone's AstaNetworkClient.BASE_URL with the Railway URL.
    (Or set ngrok auto-detect to point to Railway URL for zero-config mobile.)
11. Test: curl -H "Authorization: Bearer <token>" https://your-app.up.railway.app/api/health
```

---

### Option B — DigitalOcean $6/mo droplet (full Docker Compose)

```
1. Create a Ubuntu 22.04 droplet (at least 2 GB RAM — sentence-transformers is heavy).
   Recommended: $12/mo 2vCPU/2GB for headroom.
2. SSH in: ssh root@<droplet-ip>
3. Install Docker + Compose:
     curl -fsSL https://get.docker.com | sh
     apt install docker-compose-plugin -y
4. Clone the repo:
     git clone https://github.com/your-org/asta.git /opt/asta
     cd /opt/asta
5. Create .env from the template:
     cp deploy/prod.env.example .env
     nano .env      # fill in all secrets
6. (Optional but recommended) Buy a domain → point DNS A record to the droplet IP.
7. Build and start:
     docker compose up -d --build
8. Verify:
     docker compose ps
     curl http://localhost:8000/api/health
9. (If domain + SSL) Install nginx + certbot OUTSIDE Docker, reverse-proxy to 8000:
     apt install nginx certbot python3-certbot-nginx -y
     # Point /etc/nginx/sites-available/asta to localhost:8000
     certbot --nginx -d your-domain.com
10. Update the phone's AstaNetworkClient.BASE_URL or let ngrok auto-detect pick it up.
```

---

## 4. Mobile APK build + on-device test (Area 3)

**What works at the code level:** session_id is now persistent (SharedPreferences),
ASTAForegroundService sends session_start and turn_end over the existing WS, audio response
is played at 24 kHz (matching Deepgram TTS output), and ProactiveListenerService uses a
device-stable session ID for reminder delivery.

**What Kartik must do:**

```
1. Open ASTA MOBILE in Android Studio (Hedgehog or later).
2. Ensure the correct backend URL is in AstaNetworkClient.BASE_URL
   (either ngrok tunnel while testing locally, or the Railway/DO URL after deploy).
3. Run: flutter pub get  (in ASTA MOBILE/flutter_module/)
4. Build: Build → Generate Signed Bundle / APK → APK → Release
   OR via CLI: ./gradlew assembleRelease
5. Install: adb install -r app/build/outputs/apk/release/app-release.apk
6. Test the voice loop end-to-end:
   a. Ensure the backend is running (local uvicorn or deployed URL).
   b. Launch the app → ASTA foreground service starts → say the wake word.
   c. Speak a command → observe the "Processing..." notification.
   d. ASTA should speak back the reply through the phone speaker.
7. Test reminder delivery:
   a. Set a reminder 2 minutes from now via the app.
   b. Put the phone in airplane mode (WS drops) → then reconnect.
   c. At the scheduled time, verify the notification appears
      (requires FCM — see item 2 above — if fully offline).
```

---

## 5. Domain + SSL for DigitalOcean (Area 4, only if choosing DO)

See step 9 in Option B above.  No action needed if choosing Railway (SSL is automatic).

---

## Carry-over from Phase 1 (informational, not blocking)

### LangGraph double-interrupt edge case

If `task_manager._handle_reschedule` hits both ambiguous-task and missing-time in one
message, the second `interrupt()` during a resumed node may land on an empty `snap.next`.
Not fixed — rare in practice. Fix pattern: `content_workflow`-style phase persistence.

### Reminder offline delivery

Without FCM (item 2 above), reminders are only delivered via the live WebSocket connection.
If the phone is offline or the foreground service has been killed by the OS, the reminder is
lost server-side (it does still persist "Reminded" status to Notion — that part is fixed).
FCM (item 2) closes this gap permanently.
