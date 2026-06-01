# 🎯 TEST ASTA NOW - Step by Step

## ✅ Backend Status: RUNNING on port 8000

---

## 📱 STEP-BY-STEP TESTING GUIDE

### Step 1: Open the App (30 seconds)

1. **Unlock your Motorola Edge 50 Pro**
2. **Find the ASTA app** (look for the app icon)
3. **Tap to open**
4. **Grant permissions** when prompted:
   - ✅ Microphone access
   - ✅ Notification access
   - ✅ Record audio

**What you should see:**
- A screen with an orb/status indicator
- No chat interface (pure voice mode)
- Status showing "Listening" or "Ready"

---

### Step 2: Test Wake Word Detection (1 minute)

**Important:** Make sure you're in a quiet environment first!

1. **Hold phone about 30cm from your face**
2. **Say clearly:** "Hey Jarvis"
3. **Wait for:** Confirmation beep sound
4. **If you hear the beep:** ✅ Wake word detected!

**Troubleshooting if no beep:**
- Say it louder: "HEY JARVIS"
- Say it slower: "Hey... Jarvis"
- Check phone volume is up
- Try from closer (10cm away)

---

### Step 3: Test Voice Command (1 minute)

After you hear the beep:

1. **Immediately speak your command:**
   - "What are my tasks in routine?"
   - OR "What tasks do I have today?"
   
2. **Wait for response** (5-10 seconds)

3. **You should hear ASTA respond** through the speaker

**What's happening:**
- Your voice is being recorded
- Sent to backend via WebSocket
- Backend processes with Notion
- Response is sent back
- Text-to-speech plays the answer

---

### Step 4: Test Task Creation (1 minute)

1. **Say:** "Hey Jarvis"
2. **Wait for beep**
3. **Say:** "Add I have to attend a meeting at 8:30 pm today"
4. **Wait for response**
5. **ASTA should confirm:** "Got it boss! Added the task..."

**Verify in Notion:**
- Open your Notion Routine database
- Check if the task was created
- Should see: "Attend a meeting" at 8:30 pm

---

## 🐛 TROUBLESHOOTING

### Problem: App crashes on launch

**Solution:**
```bash
# Reinstall the app
cd "ASTA MOBILE"
./gradlew installDebug
```

### Problem: No wake word detection

**Check logs in real-time:**
```bash
# Open a new terminal and run:
adb logcat | grep -i "openwakeword\|wakeword"

# You should see:
# "OpenWakeWord Engine initialized successfully"
# "Loaded melspectrogram.onnx"
# "Loaded hey_jarvis.onnx"
```

**If you see errors:**
1. Check microphone permission granted
2. Restart the app
3. Try saying wake word louder

### Problem: Wake word detected but no recording

**Check logs:**
```bash
adb logcat | grep -i "audio\|recording"
```

**Solutions:**
1. Check microphone permission
2. Check phone volume
3. Restart app

### Problem: No response from backend

**Check WebSocket connection:**
```bash
adb logcat | grep -i "websocket\|connected"
```

**Solutions:**
1. Make sure backend is running (it is!)
2. Check if phone and PC are on same network
3. If on different networks, you need to:
   - Find PC IP: `ipconfig` (look for IPv4)
   - Update app WebSocket URL to: `ws://YOUR_PC_IP:8000/ws/conversation`

---

## 📊 MONITORING (Optional)

### Watch logs in real-time:

**Terminal 1 - Wake Word Detection:**
```bash
adb logcat | grep OpenWakeWordEngine
```

**Terminal 2 - WebSocket Connection:**
```bash
adb logcat | grep WebSocket
```

**Terminal 3 - Backend Processing:**
```bash
# Already running - check the process output
```

---

## ✅ SUCCESS CRITERIA

### Minimum Working Test:
- [ ] App opens without crashing
- [ ] "Hey Jarvis" triggers beep
- [ ] Voice command is recorded
- [ ] Response is heard through speaker

### Full Functionality Test:
- [ ] Wake word detection works consistently
- [ ] Can query tasks from Notion
- [ ] Can create new tasks
- [ ] Responses are clear and accurate
- [ ] Cooldown period works (can't trigger twice quickly)

---

## 🎯 QUICK TEST COMMANDS

Try these in order:

1. **"Hey Jarvis"** → "What are my tasks in routine?"
2. **"Hey Jarvis"** → "Add meeting at 8:30 pm today"
3. **"Hey Jarvis"** → "What's the weather?"
4. **"Hey Jarvis"** → "Tell me about my schedule"

---

## 📞 WHAT TO DO NEXT

### If Everything Works ✅
🎉 **Congratulations!** Your ASTA voice assistant is fully functional!

**Next steps:**
- Test in different environments (noisy, quiet, far away)
- Monitor battery usage over 1 hour
- Adjust sensitivity if needed (see OPENWAKEWORD_READY.md)
- Enjoy your voice assistant!

### If Something Doesn't Work ❌

**Tell me what's happening:**
1. Which step failed?
2. What error did you see?
3. What do the logs show?

**I'll help you fix it!**

---

## 🚀 START TESTING NOW!

1. **Pick up your phone**
2. **Open ASTA app**
3. **Say "Hey Jarvis"**
4. **Report back what happens!**

---

**Backend Status:** ✅ Running on port 8000
**App Status:** ✅ Installed with OpenWakeWord
**Models Status:** ✅ Loaded in assets folder

**Everything is ready - just test it!** 🎉
