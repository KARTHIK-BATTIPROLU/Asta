# ASTA React Frontend - Complete Recreation Guide

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture & Core Components](#architecture--core-components)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Step-by-Step Implementation](#step-by-step-implementation)
6. [Core Features Implementation](#core-features-implementation)
7. [Testing & Deployment](#testing--deployment)

---

## 🎯 Project Overview

The ASTA React frontend is a real-time voice assistant interface with:
- **WebSocket-based bidirectional communication**
- **Voice Activity Detection (VAD)** using AudioWorklet
- **Real-time audio streaming** (PCM format)
- **Text and voice input modes**
- **Interruption handling** (barge-in capability)
- **State machine-based conversation flow**
- **Modern dark-themed UI**

---

## 🏗️ Architecture & Core Components

### State Machine
```
IDLE → LISTENING → PROCESSING → THINKING → RESPONDING → LISTENING
  ↑                                                          ↓
  └──────────────────────────────────────────────────────────┘
```

### Core Components
1. **App.jsx** - Main application component
2. **VAD Processor** - AudioWorklet for voice activity detection
3. **PCM Player** - Custom audio player for streaming TTS
4. **WebSocket Manager** - Real-time communication handler
5. **Audio Capture** - Microphone input processing

---

## 🛠️ Technology Stack

### Core Dependencies
```json
{
  "react": "^19.2.4",
  "react-dom": "^19.2.4",
  "axios": "^1.13.6",
  "lucide-react": "^0.577.0",
  "ws": "^8.20.0"
}
```

### Dev Dependencies
```json
{
  "vite": "^8.0.1",
  "@vitejs/plugin-react": "^6.0.1",
  "eslint": "^9.39.4",
  "eslint-plugin-react-hooks": "^7.0.1",
  "eslint-plugin-react-refresh": "^0.5.2"
}
```

### Browser APIs Used
- **Web Audio API** - Audio processing and playback
- **AudioWorklet** - Low-latency audio processing
- **MediaDevices API** - Microphone access
- **WebSocket API** - Real-time communication
- **ScriptProcessor** - Audio capture (legacy but stable)

---

## 📁 Project Structure

```
frontend/
├── public/
│   ├── vad-processor.js       # AudioWorklet processor
│   ├── favicon.svg
│   └── icons.svg
├── src/
│   ├── api/
│   │   └── index.js           # API client configuration
│   ├── assets/
│   │   └── hero.png
│   ├── App.jsx                # Main application
│   ├── App.css                # Application styles
│   ├── index.css              # Global styles
│   └── main.jsx               # Entry point
├── package.json
├── vite.config.js
└── index.html
```

---

## 🚀 Step-by-Step Implementation

### Phase 1: Project Setup (30 minutes)

#### Step 1.1: Initialize Vite React Project
```bash
npm create vite@latest asta-frontend -- --template react
cd asta-frontend
npm install
```

#### Step 1.2: Install Dependencies
```bash
npm install axios lucide-react ws
npm install -D eslint eslint-plugin-react-hooks eslint-plugin-react-refresh
```

#### Step 1.3: Configure Vite
Create `vite.config.js`:
```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,  
      }
    }
  }
})
```

#### Step 1.4: Create Environment Configuration
Create `.env.local`:
```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/ws/conversation
```

---

### Phase 2: Core Audio Components (2 hours)

#### Step 2.1: Create VAD Processor (AudioWorklet)
Create `public/vad-processor.js`:

**Purpose**: Real-time voice activity detection running on audio thread

**Key Features**:
- Dynamic noise floor adaptation
- Configurable sensitivity
- Speech start/end detection
- Audio level monitoring

**Implementation Details**:
```javascript
class VADProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // Timing parameters (at 16kHz, 128 samples = 8ms per frame)
    this.minSpeechFrames = 6;      // ~48ms to trigger speech start
    this.minSilenceFrames = 312;   // ~2500ms to trigger speech end
    
    // State tracking
    this.speechFrames = 0;
    this.silenceFrames = 0;
    this.isSpeaking = false;
    
    // Dynamic noise gate
    this.silenceBuffer = new Float32Array(625); // 5 seconds history
    this.currentSilenceAvgMatch = 0.005;
    this.sensitivityMultiplier = 4.0;
  }
  
  calculateRMS(input) {
    // Root Mean Square calculation for audio level
  }
  
  updateNoiseFloor(rms) {
    // Adaptive noise floor calculation
  }
  
  process(inputs, outputs, parameters) {
    // Main processing loop
    // 1. Calculate RMS and audio level
    // 2. Compare against dynamic threshold
    // 3. Track speech/silence frames
    // 4. Emit events: speech_start, speech_end, audio_level
  }
}
```

#### Step 2.2: Create PCM Player Class
**Purpose**: Stream and play PCM audio chunks from backend

**Key Features**:
- Queue-based audio playback
- Automatic queue management
- Callback on queue empty
- Interruption support

**Implementation**:
```javascript
class PCMPlayer {
  constructor(sampleRate, onQueueEmpty) {
    this.sampleRate = sampleRate;
    this.audioCtx = new AudioContext({ sampleRate });
    this.queue = [];
    this.onQueueEmpty = onQueueEmpty;
    this.isPlaying = false;
    
    // ScriptProcessor for audio output
    this.processor = this.audioCtx.createScriptProcessor(4096, 0, 1);
    this.processor.onaudioprocess = (e) => {
      // Dequeue and play audio chunks
    };
    this.processor.connect(this.audioCtx.destination);
  }
  
  feed(float32Array) {
    // Add audio chunk to queue
  }
  
  stopAll() {
    // Clear queue and stop playback
  }
}
```

**Usage Pattern**:
1. Create player with sample rate (24000 Hz)
2. Feed Float32Array chunks as they arrive
3. Player automatically manages playback
4. Callback fires when queue empties

---

### Phase 3: State Management (1 hour)

#### Step 3.1: Define Application States
```javascript
const STATE = {
  IDLE: 'IDLE',           // Not recording, no activity
  LISTENING: 'LISTENING', // Mic active, waiting for speech
  PROCESSING: 'PROCESSING', // Sending audio to backend
  THINKING: 'THINKING',   // Backend processing (optional)
  RESPONDING: 'RESPONDING' // Playing TTS response
};
```

#### Step 3.2: State Transition Rules
```
IDLE:
  - Can transition to: LISTENING (user starts mic)
  
LISTENING:
  - Can transition to: PROCESSING (speech detected)
  - Can transition to: IDLE (user stops mic)
  
PROCESSING:
  - Can transition to: THINKING (backend processing)
  - Can transition to: RESPONDING (TTS starts)
  
THINKING:
  - Can transition to: RESPONDING (TTS starts)
  
RESPONDING:
  - Can transition to: LISTENING (TTS complete, mic still active)
  - Can transition to: IDLE (TTS complete, mic stopped)
  - Can be interrupted: LISTENING (barge-in detected)
```

#### Step 3.3: Create State Manager
```javascript
const [currentState, setCurrentState] = useState(STATE.IDLE);
const currentStateRef = useRef(STATE.IDLE);

const changeState = (newState) => {
  console.log(`STATE: ${newState}`);
  setCurrentState(newState);
  currentStateRef.current = newState;
  
  // Reset VAD on entering LISTENING
  if (newState === STATE.LISTENING && vadNodeRef.current) {
    vadNodeRef.current.port.postMessage({ type: 'reset' });
  }
};
```

---

### Phase 4: WebSocket Communication (2 hours)

#### Step 4.1: WebSocket Setup
```javascript
const WS_BASE_URL = "ws://localhost:8000/ws/conversation";
const wsRef = useRef(null);
const sessionIdRef = useRef(crypto.randomUUID());

const connectWS = () => {
  const ws = new WebSocket(WS_BASE_URL);
  wsRef.current = ws;
  
  ws.onopen = () => {
    console.log("Connected");
    ws.send(JSON.stringify({
      type: "session_start",
      session_id: sessionIdRef.current
    }));
  };
  
  ws.onmessage = handleMessage;
  ws.onerror = () => scheduleReconnect();
  ws.onclose = () => {
    // Cleanup and reconnect
  };
};
```

#### Step 4.2: Message Types & Handlers

**Outgoing Messages**:
```javascript
// Session start
{ type: "session_start", session_id: "uuid" }

// Audio data (binary)
Int16Array.buffer // PCM audio chunks

// Turn end
{ type: "turn_end" }

// Interruption
{ type: "interrupt", timestamp: Date.now(), new_sequence_id: 123 }

// Abort session
{ type: "abort" }

// Text input
{ type: "text_input", text: "user message" }
```

**Incoming Messages**:
```javascript
// Status updates
{ type: "status", status: "listening|processing|speaking|thinking|idle" }

// User transcript
{ type: "transcript", text: "user said this", turn_id: "uuid" }

// LLM response chunks
{ type: "llm_chunk", text: "response chunk", turn_id: "uuid" }

// Audio end marker
{ type: "audio_end", turn_id: "uuid" }

// Binary audio (PCM)
ArrayBuffer: [4 bytes sequence_id][PCM Int16 data]

// Error
{ type: "error", message: "error description" }
```

#### Step 4.3: Message Handler Implementation
```javascript
const handleMessage = async (event) => {
  // Handle binary audio
  if (event.data instanceof Blob || event.data instanceof ArrayBuffer) {
    const buffer = event.data instanceof Blob 
      ? await event.data.arrayBuffer() 
      : event.data;
    
    // Parse sequence ID (first 4 bytes, big-endian)
    const view = new DataView(buffer);
    const seqId = view.getUint32(0, false);
    
    // Ignore old packets
    if (seqId < lastSequenceIdRef.current) return;
    
    // Convert PCM Int16 to Float32
    const pcmData16 = new Int16Array(buffer, 4);
    const floatData = new Float32Array(pcmData16.length);
    for (let i = 0; i < pcmData16.length; i++) {
      floatData[i] = pcmData16[i] < 0 
        ? pcmData16[i] / 32768.0 
        : pcmData16[i] / 32767.0;
    }
    
    // Feed to player
    getPcmPlayer().feed(floatData);
    return;
  }
  
  // Handle JSON messages
  const data = JSON.parse(event.data);
  // ... handle each message type
};
```

---

### Phase 5: Audio Capture & VAD Integration (2 hours)

#### Step 5.1: Microphone Setup
```javascript
const startRecording = async () => {
  // 1. Request microphone access
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      noiseSuppression: true,
      echoCancellation: true,
      autoGainControl: true,
    }
  });
  
  // 2. Create AudioContext
  const audioContext = new AudioContext({ sampleRate: 24000 });
  
  // 3. Load VAD worklet
  await audioContext.audioWorklet.addModule('/vad-processor.js');
  
  // 4. Create audio nodes
  const source = audioContext.createMediaStreamSource(stream);
  const vadNode = new AudioWorkletNode(audioContext, 'vad-processor');
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  
  // 5. Connect pipeline
  source.connect(vadNode);
  source.connect(processor);
  vadNode.connect(audioContext.destination);
  processor.connect(audioContext.destination);
};
```

#### Step 5.2: PCM Capture
```javascript
const pcmBuffersRef = useRef([]);
const isCapturingRef = useRef(false);

const setupPcmCapture = () => {
  pcmBuffersRef.current = [];
  isCapturingRef.current = true;
};

processor.onaudioprocess = (e) => {
  if (!isCapturingRef.current) return;
  
  const inputData = e.inputBuffer.getChannelData(0);
  
  // Convert Float32 to Int16
  const int16Data = new Int16Array(inputData.length);
  for (let i = 0; i < inputData.length; i++) {
    let s = Math.max(-1, Math.min(1, inputData[i]));
    int16Data[i] = s < 0 ? s * 32768 : s * 32767;
  }
  
  pcmBuffersRef.current.push(int16Data);
};
```

#### Step 5.3: VAD Event Handling
```javascript
vadNode.port.onmessage = (event) => {
  const payload = event.data;
  
  switch (payload.type) {
    case 'audio_level':
      // Update UI audio meter
      setMicLevel(payload.value);
      break;
      
    case 'speech_start':
      // Handle barge-in (interruption)
      if (currentStateRef.current === STATE.RESPONDING) {
        console.log("Barge-in detected");
        
        // Stop TTS playback
        pcmPlayerRef.current.stopAll();
        
        // Increment sequence ID to ignore old audio
        lastSequenceIdRef.current += 1;
        
        // Send interrupt signal
        sendControlMessage({ 
          type: "interrupt", 
          new_sequence_id: lastSequenceIdRef.current 
        });
        
        // Return to listening
        changeState(STATE.LISTENING);
        setupPcmCapture();
      }
      break;
      
    case 'speech_end':
      // End of user speech detected
      if (currentStateRef.current === STATE.LISTENING) {
        changeState(STATE.PROCESSING);
        stopPcmCaptureAndSend();
        sendControlMessage({ type: 'turn_end' });
      }
      break;
  }
};
```

#### Step 5.4: Send Captured Audio
```javascript
const stopPcmCaptureAndSend = () => {
  if (!isCapturingRef.current) return;
  isCapturingRef.current = false;
  
  // Concatenate all buffers
  let totalLength = 0;
  for (const arr of pcmBuffersRef.current) {
    totalLength += arr.length;
  }
  
  const payload = new Int16Array(totalLength);
  let offset = 0;
  for (const arr of pcmBuffersRef.current) {
    payload.set(arr, offset);
    offset += arr.length;
  }
  
  // Send as binary
  wsRef.current.send(payload.buffer);
  pcmBuffersRef.current = [];
};
```

---

### Phase 6: UI Components (2 hours)

#### Step 6.1: Main App Structure
```jsx
function App() {
  return (
    <div className="app-container">
      {/* Header */}
      <div className="header">
        <h1>
          <Bot size={28} />
          ASTA
        </h1>
        
        <div className="controls">
          {/* Audio meter */}
          <div className="audio-meter">
            <Activity size={16} />
            <div className="audio-meter-track">
              <div 
                className="audio-meter-fill" 
                style={{ width: `${micLevel * 100}%` }}
              />
            </div>
          </div>
          
          {/* Status indicator */}
          <div className="status-indicator">
            <div className="status-dot" />
            {status}
          </div>
          
          {/* Voice toggle */}
          <button 
            className={`icon-button ${voiceEnabled ? 'active' : ''}`}
            onClick={() => setVoiceEnabled(!voiceEnabled)}
          >
            {voiceEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
          </button>
        </div>
      </div>
      
      {/* Chat window */}
      <div className="chat-window">
        {messages.map((msg, idx) => (
          <Message key={idx} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>
      
      {/* Input area */}
      <div className="input-area">
        <form onSubmit={handleTextSubmit}>
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Type a message..."
          />
          <button type="submit" className="send-button">
            <Send size={20} />
          </button>
        </form>
        
        <button 
          className={`mic-button ${isRecording ? 'recording' : ''}`}
          onClick={isRecording ? stopRecording : startRecording}
        >
          {isRecording ? <StopCircle size={24} /> : <Mic size={24} />}
        </button>
      </div>
    </div>
  );
}
```

#### Step 6.2: Message Component
```jsx
const Message = ({ message }) => {
  const isUser = message.role === 'user';
  const isTemp = message.isTemp;
  
  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className="avatar">
        {isUser ? <User size={20} /> : <Bot size={20} />}
      </div>
      <div className={`bubble ${isTemp ? 'loading' : ''}`}>
        {isTemp && <Loader2 size={16} className="spinner" />}
        {message.content}
      </div>
    </div>
  );
};
```

#### Step 6.3: Styling (App.css)
Key CSS features:
- Dark theme with CSS variables
- Gradient backgrounds
- Smooth animations
- Responsive layout
- Custom scrollbar
- Pulse animation for recording state
- Audio meter visualization

```css
:root {
  --primary: #8b5cf6;
  --primary-hover: #7c3aed;
  --bg-dark: #0f172a;
  --bg-panel: #1e293b;
  --text-main: #f8fafc;
  --border-color: #334155;
}

.mic-button.recording {
  background-color: var(--error);
  animation: pulse-ring 2s infinite;
}

@keyframes pulse-ring {
  0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
  70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
  100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}
```

---

## 🎯 Core Features Implementation

### Feature 1: Barge-In (Interruption Handling)

**Purpose**: Allow user to interrupt assistant's response

**Implementation Flow**:
1. VAD detects speech_start during RESPONDING state
2. Immediately stop PCM player queue
3. Increment sequence ID to ignore old audio packets
4. Send interrupt message to backend
5. Transition to LISTENING state
6. Reset PCM capture for new input

**Code**:
```javascript
if (payload.type === 'speech_start' && 
    currentStateRef.current === STATE.RESPONDING) {
  
  // Stop playback
  pcmPlayerRef.current.stopAll();
  
  // Increment sequence to ignore old packets
  lastSequenceIdRef.current += 1;
  
  // Notify backend
  sendControlMessage({ 
    type: "interrupt", 
    new_sequence_id: lastSequenceIdRef.current 
  });
  
  // Return to listening
  changeState(STATE.LISTENING);
  setupPcmCapture();
}
```

**Backend Requirements**:
- Must respect new_sequence_id
- Stop TTS generation
- Clear audio queue
- Return to listening state

### Feature 2: Dynamic VAD Sensitivity

**Purpose**: Adapt to different noise environments

**Implementation**:
```javascript
// UI Control
const [vadSensitivity, setVadSensitivity] = useState(4.0);

useEffect(() => {
  if (vadNodeRef.current && vadNodeRef.current.port) {
    vadNodeRef.current.port.postMessage({ 
      type: 'config', 
      sensitivity: vadSensitivity 
    });
  }
}, [vadSensitivity]);

// UI Component
<select 
  value={vadSensitivity} 
  onChange={(e) => setVadSensitivity(parseFloat(e.target.value))}
>
  <option value="2.0">Low (noisy)</option>
  <option value="4.0">Medium</option>
  <option value="6.0">High (quiet)</option>
</select>
```

**VAD Processor**:
```javascript
// In vad-processor.js
this.port.onmessage = (event) => {
  if (event.data.type === 'config') {
    this.sensitivityMultiplier = event.data.sensitivity;
  }
};

// Dynamic threshold calculation
const activeThreshold = Math.max(0.001, this.currentSilenceAvgMatch) 
                        * this.sensitivityMultiplier;
```

### Feature 3: Reconnection Logic

**Purpose**: Handle network interruptions gracefully

**Implementation**:
```javascript
const scheduleReconnect = () => {
  if (isUnmountingRef.current) return;
  if (reconnectTimeoutRef.current) return;
  
  console.log("Retrying...");
  setStatus("Retrying...");
  
  reconnectTimeoutRef.current = setTimeout(() => {
    reconnectTimeoutRef.current = null;
    connectWS();
  }, 1000);
};

ws.onerror = () => {
  if (!isUnmountingRef.current) {
    scheduleReconnect();
  }
};

ws.onclose = () => {
  wsRef.current = null;
  setStatus("Disconnected");
  
  // Kill active session
  isSessionActiveRef.current = false;
  
  // Stop mic
  if (streamRef.current) {
    streamRef.current.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  }
  
  setIsRecording(false);
  changeState(STATE.IDLE);
  
  if (!isUnmountingRef.current) {
    scheduleReconnect();
  }
};
```

**Features**:
- Automatic reconnection with 1s delay
- Prevents multiple reconnection attempts
- Cleans up resources on disconnect
- Respects component unmounting

### Feature 4: Text Input Mode

**Purpose**: Allow text-based interaction alongside voice

**Implementation**:
```javascript
const handleTextSubmit = (e) => {
  e.preventDefault();
  if (!inputText.trim()) return;
  
  // Guard against sending while processing
  if (currentStateRef.current === STATE.PROCESSING || 
      currentStateRef.current === STATE.RESPONDING) return;
  
  const textMsg = inputText.trim();
  
  // Add to UI
  setMessages(prev => [...prev, { role: 'user', content: textMsg }]);
  setInputText('');
  changeState(STATE.PROCESSING);
  
  // Ensure WS is open
  if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
    connectWS();
    setTimeout(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        sendControlMessage({ type: 'text_input', text: textMsg });
      }
    }, 500);
    return;
  }
  
  // Send immediately
  sendControlMessage({ type: 'text_input', text: textMsg });
};
```

**Backend Requirements**:
- Accept `text_input` message type
- Process text through same pipeline as voice
- Return response via same channels (llm_chunk, audio)

### Feature 5: Audio Level Visualization

**Purpose**: Visual feedback of microphone input

**Implementation**:
```javascript
// State
const [micLevel, setMicLevel] = useState(0);

// VAD sends audio_level events
vadNode.port.onmessage = (event) => {
  if (event.data.type === 'audio_level') {
    const level = Math.max(0, Math.min(1, event.data.value));
    setMicLevel(level);
  }
};

// UI Component
<div className="audio-meter">
  <Activity size={16} />
  <div className="audio-meter-track">
    <div 
      className="audio-meter-fill" 
      style={{ width: `${micLevel * 100}%` }}
    />
  </div>
</div>
```

**CSS**:
```css
.audio-meter-track {
  width: 80px;
  height: 8px;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 99px;
  overflow: hidden;
}

.audio-meter-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #f59e0b, #ef4444);
  transition: width 0.12s linear;
}
```

---

## 🔧 Advanced Implementation Details

### Audio Processing Pipeline

```
Microphone
    ↓
MediaStreamSource (Web Audio API)
    ↓
    ├─→ VAD AudioWorklet (voice detection)
    │       ↓
    │   Events: speech_start, speech_end, audio_level
    │
    └─→ ScriptProcessor (PCM capture)
            ↓
        Int16Array buffers
            ↓
        WebSocket (binary)
            ↓
        Backend STT
```

### TTS Playback Pipeline

```
Backend TTS
    ↓
WebSocket (binary PCM)
    ↓
Sequence ID check (ignore old packets)
    ↓
Convert Int16 → Float32
    ↓
PCMPlayer queue
    ↓
ScriptProcessor (output)
    ↓
AudioContext destination
    ↓
Speakers
```

### Critical Timing Considerations

1. **AEC Warmup**: 600ms delay after mic start for echo cancellation
2. **Speech Start Hysteresis**: 48ms (6 frames) to avoid false triggers
3. **Speech End Hysteresis**: 2500ms (312 frames) to avoid cutting off speech
4. **Audio Level Updates**: Throttled to 150ms intervals
5. **Reconnection Delay**: 1000ms between attempts

### Reference Management (Critical)

**Why Refs?**
- State updates are asynchronous
- Audio callbacks need immediate values
- Prevent stale closures in event handlers

**Key Refs**:
```javascript
// State tracking
const currentStateRef = useRef(STATE.IDLE);
const isRecordingRef = useRef(false);
const isSessionActiveRef = useRef(false);
const isProcessingRef = useRef(false);

// Audio nodes
const audioContextRef = useRef(null);
const audioSourceRef = useRef(null);
const vadNodeRef = useRef(null);
const captureNodeRef = useRef(null);
const streamRef = useRef(null);

// Data buffers
const pcmBuffersRef = useRef([]);
const pcmPlayerRef = useRef(null);

// WebSocket
const wsRef = useRef(null);
const sessionIdRef = useRef(crypto.randomUUID());

// Sequence tracking
const lastSequenceIdRef = useRef(0);
const activeTurnIdRef = useRef(null);

// UI tracking
const llmTempIndexRef = useRef(null);
```

**Pattern**:
```javascript
// Always update both state and ref
const changeState = (newState) => {
  setCurrentState(newState);      // For UI
  currentStateRef.current = newState; // For callbacks
};
```

### Error Handling & Edge Cases

#### 1. WebSocket Connection Failures
```javascript
const ensureWSOpen = async (timeoutMs = 12000) => {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      return true;
    }
    
    if (!ws || ws.readyState === WebSocket.CLOSED) {
      connectWS();
    }
    
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return false;
};
```

#### 2. Microphone Permission Denied
```javascript
try {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
} catch (err) {
  console.error("Mic Setup Error:", err);
  setStatus("Mic Error");
  setIsRecording(false);
  // Show user-friendly error message
}
```

#### 3. AudioWorklet Load Failure
```javascript
try {
  await audioContext.audioWorklet.addModule('/vad-processor.js');
  workletLoadedRef.current = true;
} catch (vadError) {
  console.error("VAD Init Failed:", vadError);
  // Fallback: continue without VAD, use manual controls
}
```

#### 4. Stale Audio Packets
```javascript
// Always check sequence ID
const seqId = view.getUint32(0, false);
if (seqId < lastSequenceIdRef.current) {
  return; // Ignore old packet
}
```

#### 5. Component Unmounting
```javascript
useEffect(() => {
  isUnmountingRef.current = false;
  
  // ... setup code
  
  return () => {
    isUnmountingRef.current = true;
    
    // Clear timeouts
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    // Stop audio
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }
  };
}, []);
```

#### 6. React StrictMode Double Mounting
```javascript
// Always reset unmounting flag on mount
useEffect(() => {
  isUnmountingRef.current = false;
  // ... rest of setup
}, []);
```

#### 7. Turn ID Validation
```javascript
// Ignore messages from old turns
if (data.turn_id && activeTurnIdRef.current && 
    data.turn_id !== activeTurnIdRef.current) {
  return;
}
```

---

## 🧪 Testing & Debugging

### Testing Checklist

#### Basic Functionality
- [ ] WebSocket connects on load
- [ ] Text input sends and receives responses
- [ ] Microphone permission request works
- [ ] Audio recording starts/stops correctly
- [ ] VAD detects speech start
- [ ] VAD detects speech end
- [ ] TTS audio plays correctly
- [ ] Messages display in chat

#### Advanced Features
- [ ] Barge-in interrupts TTS
- [ ] Reconnection works after disconnect
- [ ] Multiple turns work correctly
- [ ] Audio level meter updates
- [ ] Sensitivity adjustment works
- [ ] State transitions are correct
- [ ] No audio glitches or stuttering
- [ ] No memory leaks on long sessions

#### Edge Cases
- [ ] Works with no microphone
- [ ] Handles backend errors gracefully
- [ ] Recovers from network interruptions
- [ ] Handles rapid start/stop
- [ ] Works in noisy environments
- [ ] Works in quiet environments
- [ ] Multiple tabs don't interfere
- [ ] Component unmount cleans up properly

### Debugging Tools

#### Console Logging
```javascript
// State changes
console.log(`STATE: ${newState}`);

// WebSocket messages
console.log("WS Recv:", data);
console.log("WS Send:", payload);

// Audio events
console.log("speech_start detected");
console.log("speech_end detected");
console.log("Audio level:", level);
```

#### Browser DevTools
```javascript
// Check WebSocket connection
// Network tab → WS → Messages

// Check audio context state
console.log("AudioContext state:", audioContext.state);

// Check stream status
console.log("Stream active:", stream.active);
console.log("Stream tracks:", stream.getTracks());

// Check VAD worklet
console.log("Worklet loaded:", workletLoadedRef.current);

// Check PCM player queue
console.log("Queue length:", pcmPlayerRef.current.queue.length);
```

#### Common Issues & Solutions

**Issue**: No audio playback
- Check: AudioContext state (should be "running")
- Check: PCM player queue has data
- Check: Sequence IDs match
- Solution: Click page to resume AudioContext

**Issue**: VAD not detecting speech
- Check: Microphone permissions granted
- Check: Audio level meter showing activity
- Check: Sensitivity setting appropriate
- Solution: Adjust vadSensitivity value

**Issue**: Echo/feedback
- Check: Echo cancellation enabled
- Check: AEC warmup completed (600ms)
- Solution: Use headphones or increase distance

**Issue**: WebSocket disconnects
- Check: Backend is running
- Check: Correct WebSocket URL
- Check: Network connectivity
- Solution: Check reconnection logic fires

**Issue**: Stale audio playing
- Check: Sequence ID increments on interrupt
- Check: Old packets are filtered
- Solution: Verify lastSequenceIdRef logic

---

## 🚀 Deployment

### Development
```bash
npm run dev
```
Access at: http://localhost:5173

### Production Build
```bash
npm run build
```
Output: `dist/` directory

### Environment Variables
Create `.env.production`:
```env
VITE_API_BASE_URL=https://your-backend.com/api
VITE_WS_URL=wss://your-backend.com/ws/conversation
```

### Hosting Options

#### 1. Static Hosting (Vercel, Netlify)
```bash
# Build
npm run build

# Deploy dist/ folder
```

**Configuration**:
- Set environment variables in hosting dashboard
- Configure CORS on backend
- Use WSS (secure WebSocket) in production

#### 2. Docker
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
RUN npm install -g serve
CMD ["serve", "-s", "dist", "-l", "3000"]
EXPOSE 3000
```

#### 3. Nginx
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    root /var/www/asta-frontend/dist;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://backend:8000;
    }
    
    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 📦 Complete File Templates

### 1. package.json
```json
{
  "name": "asta-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "eslint .",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.13.6",
    "lucide-react": "^0.577.0",
    "react": "^19.2.4",
    "react-dom": "^19.2.4",
    "ws": "^8.20.0"
  },
  "devDependencies": {
    "@eslint/js": "^9.39.4",
    "@types/react": "^19.2.14",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.1",
    "eslint": "^9.39.4",
    "eslint-plugin-react-hooks": "^7.0.1",
    "eslint-plugin-react-refresh": "^0.5.2",
    "globals": "^17.4.0",
    "vite": "^8.0.1"
  }
}
```

### 2. index.html
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="Content-Security-Policy" 
          content="default-src 'self'; 
                   script-src 'self'; 
                   style-src 'self' 'unsafe-inline'; 
                   connect-src 'self' ws://localhost:8000 http://localhost:8000;">
    <title>ASTA - AI Voice Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

### 3. src/main.jsx
```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

### 4. src/api/index.js
```javascript
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response) {
      console.error(`API Error [${error.response.status}]:`, error.response.data);
    } else if (error.request) {
      console.error('API Error (No Response):', error.message);
    } else {
      console.error('API Error:', error.message);
    }
    return Promise.reject(error);
  }
);

export { API_BASE_URL };

export const sendTextMessage = async (text, voiceEnabled = false, sessionId = null) => {
  const response = await api.post('/chat', {
    message: text,
    voice_enabled: voiceEnabled,
    session_id: sessionId
  });
  return response.data;
};

export const sendVoiceMessage = async (audioBlob) => {
  const formData = new FormData();
  formData.append('file', audioBlob, 'recording.webm');
  const response = await api.post('/voice', formData);
  return response.data;
};
```

---

## 🎨 Customization Guide

### Changing Theme Colors
Edit CSS variables in `App.css`:
```css
:root {
  --primary: #8b5cf6;        /* Purple - main accent */
  --primary-hover: #7c3aed;  /* Darker purple */
  --secondary: #ec4899;      /* Pink - secondary accent */
  --bg-dark: #0f172a;        /* Dark background */
  --bg-panel: #1e293b;       /* Panel background */
  --text-main: #f8fafc;      /* Main text color */
  --text-muted: #94a3b8;     /* Muted text */
  --border-color: #334155;   /* Border color */
  --success: #10b981;        /* Success/online indicator */
  --error: #ef4444;          /* Error/recording indicator */
}
```

### Adjusting VAD Parameters
In `public/vad-processor.js`:
```javascript
// Speech detection timing
this.minSpeechFrames = 6;      // Lower = more sensitive to start
this.minSilenceFrames = 312;   // Lower = cuts off speech sooner

// Noise floor buffer
this.silenceBufferSize = 625;  // Larger = slower adaptation

// Default sensitivity
this.sensitivityMultiplier = 4.0; // Higher = more sensitive
```

### Modifying Audio Settings
In `App.jsx`:
```javascript
// Microphone constraints
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    noiseSuppression: true,    // Toggle noise suppression
    echoCancellation: true,    // Toggle echo cancellation
    autoGainControl: true,     // Toggle auto gain
    sampleRate: 24000,         // Change sample rate
  }
});

// AudioContext sample rate
const audioContext = new AudioContext({ sampleRate: 24000 });

// PCM Player sample rate (must match backend)
new PCMPlayer(24000, onQueueEmpty);

// AEC warmup time
await new Promise(r => setTimeout(r, 600)); // Adjust warmup delay
```

### Adding New Features

#### 1. Push-to-Talk Mode
```javascript
const [pushToTalk, setPushToTalk] = useState(false);

// Disable VAD speech_end
vadNode.port.onmessage = (event) => {
  if (event.data.type === 'speech_end' && pushToTalk) {
    return; // Ignore automatic end
  }
  // ... rest of handler
};

// Manual control
<button 
  onMouseDown={startRecording}
  onMouseUp={stopRecording}
>
  Hold to Talk
</button>
```

#### 2. Conversation History Export
```javascript
const exportConversation = () => {
  const text = messages.map(m => 
    `${m.role.toUpperCase()}: ${m.content}`
  ).join('\n\n');
  
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `conversation-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
};
```

#### 3. Voice Selection
```javascript
const [selectedVoice, setSelectedVoice] = useState('default');

// Send with text input
sendControlMessage({ 
  type: 'text_input', 
  text: textMsg,
  voice: selectedVoice 
});

// UI
<select value={selectedVoice} onChange={e => setSelectedVoice(e.target.value)}>
  <option value="default">Default</option>
  <option value="male">Male</option>
  <option value="female">Female</option>
</select>
```

#### 4. Typing Indicator
```javascript
const [isTyping, setIsTyping] = useState(false);

// In handleMessage
if (data.type === 'status' && data.status === 'thinking') {
  setIsTyping(true);
} else if (data.type === 'llm_chunk') {
  setIsTyping(false);
}

// UI Component
{isTyping && (
  <div className="message assistant">
    <div className="avatar"><Bot size={20} /></div>
    <div className="bubble loading">
      <Loader2 size={16} className="spinner" />
      Thinking...
    </div>
  </div>
)}
```

#### 5. Audio Waveform Visualization
```javascript
const [waveformData, setWaveformData] = useState(new Array(50).fill(0));

// In VAD processor
vadNode.port.onmessage = (event) => {
  if (event.data.type === 'audio_level') {
    setWaveformData(prev => [...prev.slice(1), event.data.value]);
  }
};

// UI
<div className="waveform">
  {waveformData.map((level, i) => (
    <div 
      key={i} 
      className="waveform-bar"
      style={{ height: `${level * 100}%` }}
    />
  ))}
</div>
```

#### 6. Keyboard Shortcuts
```javascript
useEffect(() => {
  const handleKeyPress = (e) => {
    // Ctrl/Cmd + M to toggle mic
    if ((e.ctrlKey || e.metaKey) && e.key === 'm') {
      e.preventDefault();
      isRecording ? stopRecording() : startRecording();
    }
    
    // Escape to stop
    if (e.key === 'Escape' && isRecording) {
      stopRecording();
    }
  };
  
  window.addEventListener('keydown', handleKeyPress);
  return () => window.removeEventListener('keydown', handleKeyPress);
}, [isRecording]);
```

---

## 🔍 Performance Optimization

### 1. Message Rendering Optimization
```javascript
import { memo } from 'react';

const Message = memo(({ message }) => {
  // ... component code
}, (prevProps, nextProps) => {
  return prevProps.message.content === nextProps.message.content &&
         prevProps.message.isTemp === nextProps.message.isTemp;
});
```

### 2. Debounce Audio Level Updates
```javascript
const lastAudioLevelSendTsRef = useRef(0);

vadNode.port.onmessage = (event) => {
  if (event.data.type === 'audio_level') {
    const now = Date.now();
    if (now - lastAudioLevelSendTsRef.current >= 150) {
      lastAudioLevelSendTsRef.current = now;
      setMicLevel(event.data.value);
    }
  }
};
```

### 3. Lazy Load Components
```javascript
import { lazy, Suspense } from 'react';

const Settings = lazy(() => import('./components/Settings'));

function App() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      {showSettings && <Settings />}
    </Suspense>
  );
}
```

### 4. Virtual Scrolling for Long Conversations
```javascript
import { useVirtualizer } from '@tanstack/react-virtual';

const parentRef = useRef();

const virtualizer = useVirtualizer({
  count: messages.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 100,
});

return (
  <div ref={parentRef} className="chat-window">
    <div style={{ height: `${virtualizer.getTotalSize()}px` }}>
      {virtualizer.getVirtualItems().map(virtualRow => (
        <Message 
          key={virtualRow.index} 
          message={messages[virtualRow.index]}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            transform: `translateY(${virtualRow.start}px)`,
          }}
        />
      ))}
    </div>
  </div>
);
```

### 5. Audio Buffer Pool
```javascript
class AudioBufferPool {
  constructor(size = 10) {
    this.pool = [];
    this.size = size;
  }
  
  acquire(length) {
    if (this.pool.length > 0) {
      const buffer = this.pool.pop();
      if (buffer.length >= length) {
        return buffer.subarray(0, length);
      }
    }
    return new Int16Array(length);
  }
  
  release(buffer) {
    if (this.pool.length < this.size) {
      this.pool.push(buffer);
    }
  }
}

const bufferPool = new AudioBufferPool();
```

### 6. WebSocket Message Batching
```javascript
const messageQueue = useRef([]);
const flushTimeoutRef = useRef(null);

const queueMessage = (message) => {
  messageQueue.current.push(message);
  
  if (!flushTimeoutRef.current) {
    flushTimeoutRef.current = setTimeout(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'batch',
          messages: messageQueue.current
        }));
        messageQueue.current = [];
      }
      flushTimeoutRef.current = null;
    }, 50);
  }
};
```

---

## 📊 Monitoring & Analytics

### 1. Performance Metrics
```javascript
const metrics = useRef({
  audioLatency: [],
  wsLatency: [],
  vadTriggers: 0,
  interruptions: 0,
});

// Measure audio latency
const audioStartTime = Date.now();
// ... when audio plays
const latency = Date.now() - audioStartTime;
metrics.current.audioLatency.push(latency);

// Log metrics
const logMetrics = () => {
  console.log('Average Audio Latency:', 
    metrics.current.audioLatency.reduce((a, b) => a + b, 0) / 
    metrics.current.audioLatency.length
  );
};
```

### 2. Error Tracking
```javascript
const logError = (error, context) => {
  const errorData = {
    message: error.message,
    stack: error.stack,
    context,
    timestamp: Date.now(),
    userAgent: navigator.userAgent,
    state: currentStateRef.current,
  };
  
  // Send to analytics service
  fetch('/api/errors', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(errorData)
  }).catch(console.error);
};

// Usage
try {
  // ... code
} catch (error) {
  logError(error, 'startRecording');
}
```

### 3. User Session Tracking
```javascript
const sessionMetrics = useRef({
  sessionId: crypto.randomUUID(),
  startTime: Date.now(),
  messageCount: 0,
  voiceInteractions: 0,
  textInteractions: 0,
  averageResponseTime: [],
});

// Track message
const trackMessage = (type) => {
  sessionMetrics.current.messageCount++;
  if (type === 'voice') {
    sessionMetrics.current.voiceInteractions++;
  } else {
    sessionMetrics.current.textInteractions++;
  }
};

// Send session data on unmount
useEffect(() => {
  return () => {
    fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sessionMetrics.current)
    }).catch(console.error);
  };
}, []);
```

---

## 🛡️ Security Considerations

### 1. Content Security Policy
```html
<meta http-equiv="Content-Security-Policy" 
      content="default-src 'self'; 
               script-src 'self'; 
               style-src 'self' 'unsafe-inline'; 
               connect-src 'self' ws://localhost:8000 wss://your-domain.com;">
```

### 2. Input Sanitization
```javascript
const sanitizeInput = (text) => {
  // Remove potentially dangerous characters
  return text
    .replace(/[<>]/g, '')
    .trim()
    .slice(0, 1000); // Max length
};

const handleTextSubmit = (e) => {
  e.preventDefault();
  const sanitized = sanitizeInput(inputText);
  if (!sanitized) return;
  // ... send sanitized input
};
```

### 3. Rate Limiting
```javascript
const rateLimiter = useRef({
  lastRequest: 0,
  minInterval: 1000, // 1 second between requests
});

const checkRateLimit = () => {
  const now = Date.now();
  if (now - rateLimiter.current.lastRequest < rateLimiter.current.minInterval) {
    console.warn('Rate limit exceeded');
    return false;
  }
  rateLimiter.current.lastRequest = now;
  return true;
};
```

### 4. Secure WebSocket Connection
```javascript
// Use WSS in production
const WS_BASE_URL = import.meta.env.PROD 
  ? "wss://your-domain.com/ws/conversation"
  : "ws://localhost:8000/ws/conversation";

// Validate origin
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "session_start",
    session_id: sessionIdRef.current,
    origin: window.location.origin
  }));
};
```

### 5. Audio Data Validation
```javascript
const validateAudioData = (buffer) => {
  // Check buffer size
  if (buffer.byteLength > 10 * 1024 * 1024) { // 10MB max
    console.error('Audio buffer too large');
    return false;
  }
  
  // Check sequence ID
  const view = new DataView(buffer);
  const seqId = view.getUint32(0, false);
  if (seqId < 0 || seqId > 1000000) {
    console.error('Invalid sequence ID');
    return false;
  }
  
  return true;
};
```

---

## 🌐 Browser Compatibility

### Supported Browsers
- ✅ Chrome 90+ (Recommended)
- ✅ Edge 90+
- ✅ Firefox 88+
- ✅ Safari 14.1+
- ✅ Opera 76+

### Feature Detection
```javascript
const checkBrowserSupport = () => {
  const features = {
    webAudio: !!(window.AudioContext || window.webkitAudioContext),
    audioWorklet: 'audioWorklet' in AudioContext.prototype,
    mediaDevices: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    webSocket: 'WebSocket' in window,
  };
  
  const unsupported = Object.entries(features)
    .filter(([_, supported]) => !supported)
    .map(([feature]) => feature);
  
  if (unsupported.length > 0) {
    console.error('Unsupported features:', unsupported);
    alert(`Your browser doesn't support: ${unsupported.join(', ')}`);
    return false;
  }
  
  return true;
};

// Check on mount
useEffect(() => {
  if (!checkBrowserSupport()) {
    setStatus('Browser Not Supported');
  }
}, []);
```

### Polyfills
```javascript
// For older browsers
if (!window.AudioContext && window.webkitAudioContext) {
  window.AudioContext = window.webkitAudioContext;
}

// Fallback for AudioWorklet
if (!('audioWorklet' in AudioContext.prototype)) {
  console.warn('AudioWorklet not supported, using ScriptProcessor fallback');
  // Implement ScriptProcessor-only VAD
}
```

---

## 📱 Mobile Considerations

### 1. Touch Events
```javascript
<button 
  onTouchStart={startRecording}
  onTouchEnd={stopRecording}
  onMouseDown={startRecording}
  onMouseUp={stopRecording}
>
  Hold to Talk
</button>
```

### 2. Responsive Design
```css
/* Mobile styles */
@media (max-width: 768px) {
  #root {
    height: 100vh;
    padding: 0;
  }
  
  .app-container {
    border-radius: 0;
    height: 100vh;
  }
  
  .header {
    padding: 1rem;
  }
  
  .header h1 {
    font-size: 1.2rem;
  }
  
  .controls {
    gap: 0.5rem;
  }
  
  .chat-window {
    padding: 1rem;
  }
  
  .message {
    max-width: 90%;
  }
  
  .input-area {
    padding: 1rem;
  }
}

/* Landscape mobile */
@media (max-width: 768px) and (orientation: landscape) {
  .chat-window {
    padding: 0.5rem;
  }
}
```

### 3. iOS Safari Fixes
```javascript
// Fix AudioContext on iOS
const resumeAudioContext = async () => {
  if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
    await audioContextRef.current.resume();
  }
};

// Resume on user interaction
useEffect(() => {
  document.addEventListener('touchstart', resumeAudioContext, { once: true });
  return () => document.removeEventListener('touchstart', resumeAudioContext);
}, []);

// Prevent zoom on input focus (iOS)
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
```

### 4. Android Chrome Fixes
```javascript
// Request wake lock to prevent screen sleep during recording
let wakeLock = null;

const requestWakeLock = async () => {
  try {
    if ('wakeLock' in navigator) {
      wakeLock = await navigator.wakeLock.request('screen');
    }
  } catch (err) {
    console.error('Wake lock error:', err);
  }
};

const releaseWakeLock = async () => {
  if (wakeLock) {
    await wakeLock.release();
    wakeLock = null;
  }
};
```

---

## 🔧 Troubleshooting Guide

### Common Issues

#### Issue: "Microphone not working"
**Symptoms**: No audio level, VAD not triggering
**Solutions**:
1. Check browser permissions (chrome://settings/content/microphone)
2. Verify microphone is not used by another app
3. Try different browser
4. Check console for getUserMedia errors
5. Test with: `navigator.mediaDevices.enumerateDevices()`

#### Issue: "No audio playback"
**Symptoms**: Messages appear but no sound
**Solutions**:
1. Click page to resume AudioContext (browser autoplay policy)
2. Check browser volume/mute settings
3. Verify AudioContext state: `audioContext.state === 'running'`
4. Check PCM player queue: `pcmPlayerRef.current.queue.length`
5. Verify backend is sending audio data

#### Issue: "Echo/feedback"
**Symptoms**: Hearing own voice, feedback loop
**Solutions**:
1. Use headphones
2. Verify echoCancellation is enabled
3. Increase AEC warmup time (600ms → 1000ms)
4. Reduce speaker volume
5. Check microphone placement

#### Issue: "VAD too sensitive/not sensitive enough"
**Symptoms**: False triggers or missing speech
**Solutions**:
1. Adjust vadSensitivity slider (2.0 - 6.0)
2. Check environment noise level
3. Adjust minSpeechFrames (lower = more sensitive)
4. Adjust minSilenceFrames (lower = faster cutoff)
5. Check audio level meter for baseline

#### Issue: "WebSocket keeps disconnecting"
**Symptoms**: Frequent reconnections, "Retrying..." status
**Solutions**:
1. Verify backend is running
2. Check WebSocket URL is correct
3. Check network connectivity
4. Verify firewall/proxy settings
5. Check backend logs for errors
6. Increase reconnection delay

#### Issue: "Barge-in not working"
**Symptoms**: Can't interrupt assistant
**Solutions**:
1. Verify speech_start event fires during RESPONDING state
2. Check lastSequenceIdRef increments
3. Verify backend respects interrupt message
4. Check PCM player stopAll() is called
5. Verify state transitions to LISTENING

#### Issue: "Audio cutting out"
**Symptoms**: Choppy or stuttering audio
**Solutions**:
1. Check network bandwidth
2. Increase audio buffer size (4096 → 8192)
3. Check CPU usage
4. Verify sample rate matches (24000 Hz)
5. Check for memory leaks

#### Issue: "Messages not appearing"
**Symptoms**: Audio works but no text
**Solutions**:
1. Check WebSocket message handler
2. Verify JSON parsing
3. Check turn_id matching
4. Verify message state updates
5. Check React DevTools for state

#### Issue: "Memory leak"
**Symptoms**: Browser slows down over time
**Solutions**:
1. Verify cleanup in useEffect return
2. Check audio nodes are disconnected
3. Verify WebSocket is closed
4. Check for orphaned timers/intervals
5. Use Chrome DevTools Memory profiler

---

## 📚 Additional Resources

### Documentation
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)
- [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)
- [MediaDevices API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [React Hooks](https://react.dev/reference/react)

### Tools
- [Chrome DevTools](https://developer.chrome.com/docs/devtools/)
- [React DevTools](https://react.dev/learn/react-developer-tools)
- [Vite Documentation](https://vitejs.dev/)

### Community & Support
- [Stack Overflow - Web Audio](https://stackoverflow.com/questions/tagged/web-audio-api)
- [Stack Overflow - React](https://stackoverflow.com/questions/tagged/reactjs)
- [GitHub Issues](https://github.com/your-repo/issues)

---

## 🎯 Implementation Checklist

### Phase 1: Setup ✓
- [ ] Initialize Vite project
- [ ] Install dependencies
- [ ] Configure Vite
- [ ] Create environment files
- [ ] Set up project structure

### Phase 2: Core Audio ✓
- [ ] Create VAD processor (AudioWorklet)
- [ ] Implement PCM player class
- [ ] Test audio capture
- [ ] Test audio playback
- [ ] Verify VAD detection

### Phase 3: State Management ✓
- [ ] Define state machine
- [ ] Implement state transitions
- [ ] Add state guards
- [ ] Test state flow
- [ ] Add state logging

### Phase 4: WebSocket ✓
- [ ] Implement connection logic
- [ ] Add message handlers
- [ ] Implement reconnection
- [ ] Add error handling
- [ ] Test all message types

### Phase 5: Audio Integration ✓
- [ ] Set up microphone capture
- [ ] Integrate VAD events
- [ ] Implement PCM capture
- [ ] Send audio to backend
- [ ] Receive and play TTS

### Phase 6: UI ✓
- [ ] Create main layout
- [ ] Add message components
- [ ] Implement input controls
- [ ] Add audio meter
- [ ] Style components
- [ ] Add animations

### Phase 7: Features ✓
- [ ] Implement barge-in
- [ ] Add text input mode
- [ ] Add sensitivity control
- [ ] Implement reconnection
- [ ] Add status indicators

### Phase 8: Testing ✓
- [ ] Test basic functionality
- [ ] Test edge cases
- [ ] Test on multiple browsers
- [ ] Test on mobile devices
- [ ] Performance testing
- [ ] Load testing

### Phase 9: Optimization ✓
- [ ] Optimize rendering
- [ ] Add memoization
- [ ] Implement lazy loading
- [ ] Optimize audio buffers
- [ ] Add monitoring

### Phase 10: Deployment ✓
- [ ] Build production bundle
- [ ] Configure environment
- [ ] Set up hosting
- [ ] Configure SSL/WSS
- [ ] Test production build

---

## 🚦 Quick Start Commands

```bash
# 1. Create new project
npm create vite@latest asta-frontend -- --template react
cd asta-frontend

# 2. Install dependencies
npm install axios lucide-react ws

# 3. Copy files from this guide:
# - public/vad-processor.js
# - src/App.jsx
# - src/App.css
# - src/api/index.js
# - vite.config.js
# - .env.local

# 4. Start development server
npm run dev

# 5. Open browser
# http://localhost:5173

# 6. Build for production
npm run build

# 7. Preview production build
npm run preview
```

---

## 📝 Summary

This guide provides a complete blueprint for recreating the ASTA React frontend with:

✅ **Real-time voice interaction** using Web Audio API
✅ **Voice Activity Detection** with AudioWorklet
✅ **WebSocket communication** for bidirectional streaming
✅ **Barge-in capability** for natural interruptions
✅ **State machine** for robust conversation flow
✅ **Modern UI** with dark theme and animations
✅ **Text and voice modes** for flexible interaction
✅ **Error handling** and reconnection logic
✅ **Mobile support** with responsive design
✅ **Performance optimizations** for smooth experience

### Key Technologies
- React 19 with Hooks
- Vite for build tooling
- Web Audio API for audio processing
- AudioWorklet for low-latency VAD
- WebSocket for real-time communication
- Lucide React for icons

### Estimated Implementation Time
- **Basic Setup**: 30 minutes
- **Core Audio**: 2 hours
- **State Management**: 1 hour
- **WebSocket**: 2 hours
- **Audio Integration**: 2 hours
- **UI Components**: 2 hours
- **Testing & Polish**: 2-3 hours
- **Total**: ~12-13 hours

### Next Steps
1. Follow the implementation phases in order
2. Test each phase before moving to the next
3. Customize styling and features as needed
4. Deploy to production environment
5. Monitor and optimize based on usage

---

**Created**: 2026-05-18
**Version**: 1.0.0
**Author**: ASTA Development Team
