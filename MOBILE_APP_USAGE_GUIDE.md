# ASTA Mobile App - Usage Guide

## ✅ App Successfully Installed!

Your ASTA voice assistant app is now installed on your **Motorola Edge 50 Pro**.

---

## 🎯 Current Status

### What Works ✅
- ✅ App installed and ready to run
- ✅ Pure voice UI (no chat interface)
- ✅ WebSocket connection to backend
- ✅ Voice recording and streaming
- ✅ Audio playback for responses

### What's Disabled ⚠️
- ⚠️ **Wake word detection is DISABLED** (stub mode)
- The app will run but won't detect "Hey Jarvis"
- You'll need to manually trigger voice recording

---

## 📱 How to Use the App

### Step 1: Start the Backend
Make sure your backend server is running:
```bash
# Backend should already be running on port 8000
# If not, start it with:
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 2: Launch the App
1. Open the ASTA app on your phone
2. Grant microphone and notification permissions
3. The app will show an orb/status indicator

### Step 3: Connect to Backend
The app will automatically try to connect to:
- `ws://localhost:8000/ws/conversation` (if on same device)
- OR update the WebSocket URL in the app settings

**Important:** If your phone and PC are on different networks, you'll need to:
1. Find your PC's IP address: `ipconfig` (Windows) or `ifconfig` (Linux/Mac)
2. Update the WebSocket URL in the app to: `ws://YOUR_PC_IP:8000/ws/conversation`

### Step 4: Test Voice Recording
Since wake word is disabled, you'll need to manually trigger recording:
- Look for a microphone button or tap the orb
- Speak your command
- The app will send it to the backend
- You'll hear the response

---

## 🔧 Enabling Wake Word Detection

Currently, wake word detection is **disabled** (stub mode). To enable it, choose one of these options:

### Option A: Porcupine (Recommended) ⭐
**Time:** 10 minutes

1. Get free API key from https://console.picovoice.ai/
2. Follow instructions in `PORCUPINE_ALTERNATIVE.md`
3. Rebuild and reinstall the app

**Benefits:**
- Production-ready
- Battery optimized
- Simple implementation
- Reliable

### Option B: OpenWakeWord
**Time:** 2-3 hours

1. Run: `python extract_wake_word_models.py`
2. Run: `setup_android_openwakeword.bat` (Windows)
3. Rebuild and reinstall the app

**Benefits:**
- 100% free
- No API keys
- Customizable

---

## 🐛 Troubleshooting

### App Won't Connect to Backend
**Problem:** WebSocket connection fails

**Solutions:**
1. Check backend is running: `curl http://localhost:8000/health`
2. Check firewall allows port 8000
3. If phone and PC on different networks:
   - Use ngrok: `ngrok http 8000`
   - Update app WebSocket URL to ngrok URL

### No Audio Response
**Problem:** App receives response but no sound

**Solutions:**
1. Check phone volume is up
2. Check app has audio permissions
3. Look at logcat for TTS errors: `adb logcat | grep ASTA`

### App Crashes on Launch
**Problem:** App crashes immediately

**Solutions:**
1. Check logcat: `adb logcat | grep AndroidRuntime`
2. Grant all permissions in Settings > Apps > ASTA
3. Reinstall: `cd "ASTA MOBILE" && ./gradlew installDebug`

---

## 📊 App Architecture

```
┌─────────────────────────────────────────┐
│         ASTA Mobile App                 │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │   VoiceAssistantActivity         │  │
│  │   (Pure Voice UI - Orb Display)  │  │
│  └──────────────────────────────────┘  │
│                 │                       │
│                 ▼                       │
│  ┌──────────────────────────────────┐  │
│  │   WakeWordService                │  │
│  │   (STUB - Disabled)              │  │
│  └──────────────────────────────────┘  │
│                 │                       │
│                 ▼                       │
│  ┌──────────────────────────────────┐  │
│  │   AudioRecorder                  │  │
│  │   (Captures voice)               │  │
│  └──────────────────────────────────┘  │
│                 │                       │
│                 ▼                       │
│  ┌──────────────────────────────────┐  │
│  │   WebSocket Client               │  │
│  │   (Streams to backend)           │  │
│  └──────────────────────────────────┘  │
│                 │                       │
└─────────────────┼───────────────────────┘
                  │
                  ▼
         Backend Server (Port 8000)
```

---

## 🔍 Viewing Logs

To see what's happening in the app:

```bash
# View all ASTA logs
adb logcat | grep -i asta

# View wake word service logs
adb logcat | grep WakeWordService

# View WebSocket logs
adb logcat | grep WebSocket

# View errors only
adb logcat *:E | grep ASTA
```

---

## 🚀 Next Steps

### Immediate (App is Running)
1. ✅ App installed
2. ⏳ Test voice recording manually
3. ⏳ Verify backend connection
4. ⏳ Test end-to-end flow

### Short Term (Enable Wake Word)
1. ⏳ Choose: Porcupine or OpenWakeWord
2. ⏳ Follow setup guide
3. ⏳ Rebuild and test
4. ⏳ Verify "Hey Jarvis" detection

### Long Term (Polish)
1. ⏳ Optimize battery usage
2. ⏳ Add UI feedback animations
3. ⏳ Improve error handling
4. ⏳ Add settings screen

---

## 📞 Testing Checklist

### Basic Functionality
- [ ] App launches without crashing
- [ ] Permissions granted (microphone, notifications)
- [ ] Orb/status indicator visible
- [ ] Backend connection established

### Voice Recording
- [ ] Can trigger recording manually
- [ ] Audio is captured
- [ ] Audio is sent to backend
- [ ] Response is received

### Backend Integration
- [ ] WebSocket connects successfully
- [ ] Voice data streams correctly
- [ ] Backend processes request
- [ ] Response plays through speaker

### Wake Word (After Enabling)
- [ ] "Hey Jarvis" detected
- [ ] Recording starts automatically
- [ ] Cooldown period works
- [ ] Battery usage acceptable

---

## 💡 Tips

1. **Keep backend running** - The app needs the backend server
2. **Check network** - Phone and PC must be able to communicate
3. **Monitor logs** - Use `adb logcat` to debug issues
4. **Test incrementally** - Verify each component works before moving on
5. **Enable wake word later** - Get basic functionality working first

---

## 🎉 Success!

Your ASTA mobile app is now installed and ready to use!

**Current State:**
- ✅ App running on device
- ✅ Backend ready
- ⏳ Wake word detection (to be enabled)

**Next:** Test the app and decide if you want to enable wake word detection with Porcupine or OpenWakeWord.

---

## 📚 Related Documentation

- `README_START_HERE.md` - Project overview
- `PORCUPINE_ALTERNATIVE.md` - Enable wake word (recommended)
- `ANDROID_OPENWAKEWORD_SETUP.md` - Alternative wake word setup
- `FINAL_CHECKLIST.md` - Complete task list
