# ASTA Mobile App - Quick Start

## 🚀 One-Command Setup

```bash
python start_asta.py
```

That's it! This will:
1. ✅ Check/start ngrok
2. ✅ Get the ngrok URL
3. ✅ Update Android app config
4. ✅ Start the backend
5. ✅ Show you the connection URL

## 📱 Then Build the App

1. Open `ASTA MOBILE` in Android Studio
2. Click Run ▶️
3. The app automatically connects!

## 🔄 If ngrok URL Changes

Just run:
```bash
python get_ngrok_url.py
```

Then rebuild the app.

## 🎨 What's New

### Beautiful UI
- Modern Material Design 3
- Purple gradient theme
- Smooth animations
- Clean chat bubbles
- Status indicators

### Smart Connection
- Auto-detects ngrok URL
- No manual configuration
- Fallback to manual entry
- Connection health checks

## 📋 Manual Steps (if needed)

1. **Start ngrok:**
   ```bash
   ngrok http 8000
   ```

2. **Start backend:**
   ```bash
   python run.py
   ```

3. **Update app config:**
   ```bash
   python get_ngrok_url.py
   ```

4. **Build & Run** in Android Studio

## 🔍 Check Status

- ngrok dashboard: http://127.0.0.1:4040
- Backend health: http://your-ngrok-url/api/health
- ngrok URL endpoint: http://your-ngrok-url/api/ngrok-url

## 💡 Tips

- Keep ngrok running (URL changes on restart)
- Use `start_asta.py` for easiest setup
- Check status card in app for connection state
- Tap mic button for voice input
- Settings button for manual URL entry

## 🐛 Troubleshooting

**Can't connect?**
```bash
python get_ngrok_url.py
```

**ngrok not found?**
Download from: https://ngrok.com/download

**Backend not starting?**
```bash
pip install -r requirements.txt
python run.py
```

---

**Need more details?** See [MOBILE_APP_SETUP.md](MOBILE_APP_SETUP.md)
