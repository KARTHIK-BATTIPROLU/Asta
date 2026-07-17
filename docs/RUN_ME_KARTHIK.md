# Run ASTA — Karthik's Demo Checklist

## 1. Frontend config

```powershell
copy frontend\config.example.js frontend\config.js
```

Edit `frontend/config.js` — paste from your `.env`:

- `BEARER_TOKEN` ← value of `ASTA_API_BEARER_TOKEN`
- `DEVICE_ID` ← your registered device ID (same as `ASTA_DEVICE_ID` in `.env`)

## 2. Start backend

```powershell
cd C:\Users\Karthik\OneDrive\Desktop\ASTA
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

**You should see in logs:** `Starting Outbox Worker...`

## 3. Start frontend

```powershell
cd frontend
npx serve .
```

Open the URL shown (usually `http://localhost:3000`).

## 4. What you should see

1. **Blue orb** on screen
2. If using wake-word trigger: say **"hey asta"** — orb arms for listening
3. During a turn, orb states cycle: **idle → listening → thinking → speaking → idle**
4. Text replies appear in the UI alongside audio

## 5. Memory demo (run once before the live demo)

In a second terminal, with backend running:

```powershell
python scripts/prove_memory_loop.py --device-id YOUR_DEVICE_ID
```

Then in the browser, ask: **"What's my favorite chess opening?"**

ASTA should answer with **Najdorf** — memory from a prior session, not hardcoded.

## 6. Private mode demo (optional)

```powershell
python scripts/prove_memory_loop.py --private --device-id YOUR_DEVICE_ID
```

In a live session you can also say **"private mode on"** — ASTA confirms, and that chat won't be extracted into memory.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| WS auth rejected | Token/device mismatch — re-check `config.js` vs `.env` and Mongo `registered_devices` |
| No memory recall | Check backend logs for `[Outbox] Successfully extracted` after closing a session |
| Orb stuck | Refresh page; confirm backend health at `http://127.0.0.1:8000/api/health/` |
