import React, { useState, useRef, useEffect } from 'react';
import { Mic, Bot, User, Loader2, StopCircle, Volume2, VolumeX, Activity, PauseCircle, PlayCircle, Send, Bell, HelpCircle } from 'lucide-react';
import './App.css';
import JarvisOrb from './orb/JarvisOrb';

// CSP-compliant WebSocket URL configuration
const WS_TOKEN = import.meta.env.VITE_ASTA_API_TOKEN || "asta-secure-token-2026";
const WS_DEVICE_ID = import.meta.env.VITE_ASTA_DEVICE_ID || "asta-web-client";
const WS_HOST = import.meta.env.VITE_ASTA_WS_HOST || "ws://localhost:8000";
const WS_BASE_URL = `${WS_HOST}/ws/conversation?token=${encodeURIComponent(WS_TOKEN)}&device_id=${encodeURIComponent(WS_DEVICE_ID)}`;

// TASK 1: DEFINE STATES
const STATE = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  PROCESSING: 'PROCESSING',
  THINKING: 'THINKING',
};

class PCMPlayer {
    constructor(sampleRate, onQueueEmpty) {
        this.sampleRate = sampleRate;
        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate });
        this.queue = [];
        this.onQueueEmpty = onQueueEmpty;
        this.isPlaying = false;
        
        this.processor = this.audioCtx.createScriptProcessor(4096, 0, 1);
        this.processor.onaudioprocess = (e) => {
            const output = e.outputBuffer.getChannelData(0);
            let written = 0;
            
            while (written < output.length && this.queue.length > 0) {
                const chunk = this.queue[0];
                const space = output.length - written;
                const available = chunk.length;
                
                if (available <= space) {
                    output.set(chunk, written);
                    written += available;
                    this.queue.shift();
                } else {
                    output.set(chunk.subarray(0, space), written);
                    this.queue[0] = chunk.subarray(space);
                    written += space;
                }
            }
            
            for (let i = written; i < output.length; i++) {
                output[i] = 0;
            }
            
            if (this.queue.length === 0 && this.isPlaying) {
                this.isPlaying = false;
                if (this.onQueueEmpty) setTimeout(this.onQueueEmpty, 0);
            } else if (written > 0) {
                this.isPlaying = true;
            }
        };
        this.processor.connect(this.audioCtx.destination);
    }

    feed(float32Array) {
        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }
        this.queue.push(float32Array);
    }

    stopAll() {
        this.queue = [];
        this.isPlaying = false;
    }
}

function App() {
  const [inputText, setInputText] = useState('');
  const [currentState, setCurrentState] = useState(STATE.IDLE);
  const currentStateRef = useRef(STATE.IDLE);

  const changeState = (newState) => {
    console.log(`STATE: ${newState}`);
    
    if (newState === STATE.LISTENING && vadNodeRef.current && vadNodeRef.current.port) {
        vadNodeRef.current.port.postMessage({ type: 'reset' });
    }

    setCurrentState(newState);
    currentStateRef.current = newState;
    if (newState !== STATE.PROCESSING) {
        isProcessingRef.current = false;
    }

    // ASTA SEAM WIRING
    if (orbRef.current) {
        let mapped = 'idle';
        if (newState === STATE.LISTENING) mapped = 'listening';
        else if (newState === STATE.THINKING || newState === STATE.PROCESSING) mapped = 'thinking';
        else if (newState === STATE.RESPONDING) mapped = 'speaking';
        orbRef.current.setAstaState(mapped);
    }
  };

  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi! I'm Asta. How can I help you today?" }
  ]);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [status, setStatus] = useState("Online");
  const [micLevel, setMicLevel] = useState(0);
  const [isListeningPaused, setIsListeningPaused] = useState(false);
  const [interruptionProfile, setInterruptionProfile] = useState('balanced');
  const [vadSensitivity, setVadSensitivity] = useState(4.0);
  
  const captureNodeRef = useRef(null);
  const pcmBuffersRef = useRef([]);
  const isCapturingRef = useRef(false);

  const isResponseCompleteRef = useRef(false);
  const pcmPlayerRef = useRef(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const wsRef = useRef(null); 
  const orbRef = useRef(null); 
  const sessionIdRef = useRef((() => {
    const stored = localStorage.getItem('asta_session_id');
    if (stored) return stored;
    const fresh = crypto.randomUUID();
    localStorage.setItem('asta_session_id', fresh);
    return fresh;
  })());
  const wsConnectStartedAtRef = useRef(0);
  const llmTempIndexRef = useRef(null);
  const lastSequenceIdRef = useRef(0);
  const isProcessingRef = useRef(false);
  const activeTurnIdRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const isUnmountingRef = useRef(false);
  const lastSpeechTimeRef = useRef(Date.now());
  const silenceIntervalRef = useRef(null);
  
  // VAD Refs
  const audioContextRef = useRef(null);
  const audioSourceRef = useRef(null);
  const vadNodeRef = useRef(null);
  const lastAudioLevelSendTsRef = useRef(0);
  const streamRef = useRef(null);
  const isStartingRef = useRef(false);
  const isRecordingRef = useRef(false);
  const isSessionActiveRef = useRef(false);
  const workletLoadedRef = useRef(false);


  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  useEffect(() => {
    if (vadNodeRef.current && vadNodeRef.current.port) {
      vadNodeRef.current.port.postMessage({ type: 'config', sensitivity: vadSensitivity });
    }
  }, [vadSensitivity]);

  const sendControlMessage = (payload) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  };

  const getPcmPlayer = () => {
      if (!pcmPlayerRef.current) {
          pcmPlayerRef.current = new PCMPlayer(24000, () => {
              if (currentStateRef.current === STATE.IDLE) return;
              
              if (isResponseCompleteRef.current) {
                  isResponseCompleteRef.current = false;
                  setStatus("Online");
                  if (currentStateRef.current === STATE.RESPONDING || currentStateRef.current === STATE.PROCESSING || currentStateRef.current === STATE.THINKING) {
                      setTimeout(() => {
                          if (currentStateRef.current === STATE.IDLE) return;
                          changeState((isRecordingRef.current && isSessionActiveRef.current) ? STATE.LISTENING : STATE.IDLE);
                          if (isRecordingRef.current && isSessionActiveRef.current) resumePcmCapture();
                      }, 500);
                  }
              }
          });
      }
      return pcmPlayerRef.current;
  };

  const setupPcmCapture = () => {
    if (!isSessionActiveRef.current) return;
    
    // Reset our silence clock for the new session
    lastSpeechTimeRef.current = Date.now();
    
    pcmBuffersRef.current = [];
    isCapturingRef.current = true;
    console.log("PCM Capture restarted for next turn");
  };

  const stopPcmCaptureAndSend = () => {
    if (!isCapturingRef.current) return;
    isCapturingRef.current = false;
    
    if (pcmBuffersRef.current.length > 0 && wsRef.current && wsRef.current.readyState === 1) {
      let totalLength = 0;
      for (const arr of pcmBuffersRef.current) totalLength += arr.length;
      
      const payload = new Int16Array(totalLength);
      let offset = 0;
      for (const arr of pcmBuffersRef.current) {
        payload.set(arr, offset);
        offset += arr.length;
      }
      wsRef.current.send(payload.buffer);
    }
    pcmBuffersRef.current = [];
    console.log("PCM Capture stopped and sent.");
  };

  useEffect(() => {
    if (!isSessionActiveRef.current) return;
    if ((currentState === STATE.LISTENING || currentState === STATE.RESPONDING) && isRecordingRef.current && streamRef.current) {
      if (!isCapturingRef.current) {
        setupPcmCapture();
      }
    }
  }, [currentState]);

  const resumePcmCapture = () => {
    if (!isSessionActiveRef.current) return;
    if (isRecordingRef.current && streamRef.current) {
      setupPcmCapture();
    }
  };

  const initPlaybackContext = () => {
      getPcmPlayer();
  };

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

  const handleMessage = async (event) => {
    if (event.data instanceof Blob || event.data instanceof ArrayBuffer) {
      let buffer;
      if (event.data instanceof Blob) {
          buffer = await event.data.arrayBuffer();
      } else {
          buffer = event.data;
      }
      
      if (buffer.byteLength < 4) return;
      
      const view = new DataView(buffer);
      const seqId = view.getUint32(0, false); // Big-Endian
      
      if (seqId < lastSequenceIdRef.current) {
          return; // Ignore ghost packet
      }
      
      // RAW PCM PARSING: Bypass decodeAudioData entirely!
      const player = getPcmPlayer();
      
      const pcmData16 = new Int16Array(buffer, 4); 
      const floatData = new Float32Array(pcmData16.length);
      for (let i = 0; i < pcmData16.length; i++) {
          floatData[i] = pcmData16[i] < 0 ? pcmData16[i] / 32768.0 : pcmData16[i] / 32767.0;
      }
      
      player.feed(floatData);
      return;
    }

    let data;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      console.error('Failed to parse WS JSON message:', err);
      return;
    }

    if (data.type === 'audio') {
      const b64Data = data.data;
      if (!b64Data) return;
      
      const raw = window.atob(b64Data);
      const rawLength = raw.length;
      const u8 = new Uint8Array(rawLength);
      for (let i = 0; i < rawLength; i++) {
        u8[i] = raw.charCodeAt(i);
      }
      
      const buffer = u8.buffer;
      if (buffer.byteLength < 4) return;
      
      const view = new DataView(buffer);
      const seqId = view.getUint32(0, false); // Big-Endian
      
      if (seqId < lastSequenceIdRef.current) {
          return; // Ignore ghost packet
      }
      
      // RAW PCM PARSING: Bypass decodeAudioData entirely!
      const player = getPcmPlayer();
      
      const pcmData16 = new Int16Array(buffer, 4); 
      const floatData = new Float32Array(pcmData16.length);
      for (let i = 0; i < pcmData16.length; i++) {
          floatData[i] = pcmData16[i] < 0 ? pcmData16[i] / 32768.0 : pcmData16[i] / 32767.0;
      }
      
      player.feed(floatData);
      return;
    }

    console.log("WS Recv:", data);

    if (data.type === 'status') {
      const st = data.status.toLowerCase();
      if (st === 'thinking') changeState(STATE.THINKING);
      else if (st === 'processing') changeState(STATE.PROCESSING);
      else if (st === 'speaking') changeState(STATE.RESPONDING);
      else if (st === 'listening') changeState(STATE.LISTENING);
      else if (st === 'idle') changeState(STATE.IDLE);
    }

    if (data.type === 'transcript') {
      if (data.turn_id && activeTurnIdRef.current && data.turn_id !== activeTurnIdRef.current) return;
      if (data.text) {
        setMessages(prev => {
          if (prev.length > 0 && prev[prev.length - 1].role === 'user' && prev[prev.length - 1].content === data.text) {
            return prev;
          }
          return [...prev, { role: 'user', content: data.text }];
        });
      }
      return;
    }

    if (data.type === 'asta_proactive') {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || '',
        proactive: true,
        trigger: data.trigger,
      }]);
      if (data.audio_base64) {
        try {
          const audio = new Audio(`data:audio/mpeg;base64,${data.audio_base64}`);
          audio.play().catch(err => console.warn('Proactive audio playback blocked:', err));
        } catch (err) {
          console.warn('Proactive audio failed:', err);
        }
      }
      return;
    }

    if (data.type === 'workflow_result') {
      if (data.turn_id && activeTurnIdRef.current && data.turn_id !== activeTurnIdRef.current) return;
      setMessages(prev => {
        const idx = llmTempIndexRef.current;
        if (idx == null || !prev[idx]) return prev;
        const next = [...prev];
        next[idx] = {
          ...next[idx],
          taskData: data.task_data || {},
          awaitingClarification: !!data.awaiting_clarification,
        };
        return next;
      });
      return;
    }

    if (data.type === 'llm_chunk') {
      if (data.turn_id && activeTurnIdRef.current && data.turn_id !== activeTurnIdRef.current) return;
      const chunk = data.text || '';
      if (!chunk) return;

      setMessages(prev => {
        if (
          llmTempIndexRef.current == null ||
          !prev[llmTempIndexRef.current] ||
          !prev[llmTempIndexRef.current].isTemp
        ) {
          const next = [...prev, { role: 'assistant', content: chunk, isTemp: true }];
          llmTempIndexRef.current = next.length - 1;
          return next;
        }

        const next = [...prev];
        next[llmTempIndexRef.current] = {
          ...next[llmTempIndexRef.current],
          content: `${next[llmTempIndexRef.current].content}${chunk}`
        };
        return next;
      });
      return;
    }

    if (data.type === 'audio_end') {
      if (data.turn_id && activeTurnIdRef.current && data.turn_id !== activeTurnIdRef.current) return;
      isResponseCompleteRef.current = true;
      setMessages(prev => {
        if (llmTempIndexRef.current == null || !prev[llmTempIndexRef.current]) return prev;
        const next = [...prev];
        next[llmTempIndexRef.current] = {
          ...next[llmTempIndexRef.current],
          isTemp: false
        };
        llmTempIndexRef.current = null;
        return next;
      });

      // Guard: If audio playback finished before this packet arrived, trigger transition immediately
      if (!pcmPlayerRef.current || pcmPlayerRef.current.queue.length === 0) {
          isResponseCompleteRef.current = false;
          setStatus("Online");
          if (currentStateRef.current === STATE.RESPONDING || currentStateRef.current === STATE.PROCESSING || currentStateRef.current === STATE.THINKING) {
              setTimeout(() => {
                  if (currentStateRef.current === STATE.IDLE) return;
                  changeState((isRecordingRef.current && isSessionActiveRef.current) ? STATE.LISTENING : STATE.IDLE);
                  if (isRecordingRef.current && isSessionActiveRef.current) resumePcmCapture();
              }, 500);
          }
      }
      return;
    }

    if (data.type === 'status') {
      const backendStatus = data.status;
      setStatus(backendStatus || 'Online');
      
      // Guard: kill switch (IDLE) is authoritative — backend cannot override
      if (currentStateRef.current === STATE.IDLE) return;
      
      if (backendStatus === 'processing') {
         if (data.turn_id) activeTurnIdRef.current = data.turn_id;
         
         if (pcmPlayerRef.current) {
             pcmPlayerRef.current.stopAll();
         }
         
         if (llmTempIndexRef.current !== null) {
            setMessages(prev => {
                const next = [...prev];
                if (next[llmTempIndexRef.current] && next[llmTempIndexRef.current].isTemp) {
                    next.splice(llmTempIndexRef.current, 1);
                }
                return next;
            });
            llmTempIndexRef.current = null;
         }
         changeState(STATE.PROCESSING);
      } else if (backendStatus === 'speaking') {
         changeState(STATE.RESPONDING);
      } else if (backendStatus === 'listening') {
         // Backend signals: empty transcript or ready for next input
         // Only return to LISTENING if mic session is still active
         if (isRecordingRef.current) {
           changeState(STATE.LISTENING);
         }
      } else if (backendStatus === 'idle') {
         // Backend explicitly idle — frontend already authoritative
      }
      return;
    }

    if (data.type === 'error') {
      console.error('[WS Error]', data.message);
      setStatus('Error');
      // Clear any pending TTS chunks (stale data)
      if (pcmPlayerRef.current) pcmPlayerRef.current.stopAll();
      llmTempIndexRef.current = null;
      // Recover state: if session active → back to LISTENING, otherwise IDLE
      if (isSessionActiveRef.current && isRecordingRef.current) {
        changeState(STATE.LISTENING);
        // Restart PCM capture for next turn
        setupPcmCapture();
      } else {
        changeState(STATE.IDLE);
      }
    }
  };

  const connectWS = () => {
    if (isUnmountingRef.current) return;
    if (wsRef.current && wsRef.current.readyState === 1) {
      console.log("WS already active, skip reconnect");
      return;
    }
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    // Reset old reference safely
    if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
    }

    console.log("Connecting to WebSocket:", WS_BASE_URL);
    setStatus("Connecting...");

    wsConnectStartedAtRef.current = Date.now();
    const ws = new WebSocket(WS_BASE_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("Connected");
      setStatus("Connected");

      ws.send(JSON.stringify({
        type: "session_start",
        session_id: sessionIdRef.current
      }));
    };

    ws.onmessage = handleMessage;

    ws.onerror = () => {
      if (isUnmountingRef.current) return;
      console.log("WS error -> retrying...");
      scheduleReconnect();
    };

    ws.onclose = () => {
      const wasUnmounting = isUnmountingRef.current;
      wsRef.current = null;
      console.log("Disconnected");
      setStatus("Disconnected");

      // Kill session on WS close — prevents any callback from restarting
      isSessionActiveRef.current = false;

      if (isCapturingRef.current) {
        stopPcmCaptureAndSend();
        console.log("Mic stopped due to WS close");
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      setIsRecording(false);
      setIsListeningPaused(false);
      changeState(STATE.IDLE);

      if (wasUnmounting) return;
      console.log("WS closed -> reconnecting...");
      scheduleReconnect();
    };
  };

  const ensureWSOpen = async (timeoutMs = 12000) => {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        return true;
      }

      if (!ws || ws.readyState === WebSocket.CLOSED) {
        connectWS();
      } else if (
        ws.readyState === WebSocket.CONNECTING &&
        wsConnectStartedAtRef.current &&
        Date.now() - wsConnectStartedAtRef.current > 3500
      ) {
        // Restart stale connecting sockets so retries can continue while user waits.
        try {
          ws.close();
        } catch (e) {
          console.error("Failed to reset stale websocket:", e);
        }
      }

      await new Promise(resolve => setTimeout(resolve, 100));
    }
    return false;
  };

  useEffect(() => {
    // In React dev StrictMode, cleanup can run during mount simulation.
    // Always reset this flag when the component effect starts.
    isUnmountingRef.current = false;

    if (wsRef.current) return; // prevent duplicate

    const startTimer = setTimeout(() => {
      connectWS();
    }, 500);

    return () => {
      isUnmountingRef.current = true;
      clearTimeout(startTimer);

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (silenceIntervalRef.current) {
        clearInterval(silenceIntervalRef.current);
        silenceIntervalRef.current = null;
      }

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Focus input on load
    inputRef.current?.focus();
  }, []);

  const startRecording = async () => {
    // TASK 2: CONTROL MIC START
    // TASK 9: BLOCK ALL INVALID ACTIONS (DO NOT start mic if PROCESSING)
    if (currentStateRef.current === STATE.PROCESSING || currentStateRef.current === STATE.RESPONDING || currentStateRef.current === STATE.THINKING) return;
    if (isRecordingRef.current || isStartingRef.current) return;
    
    changeState(STATE.LISTENING);
    isStartingRef.current = true;
    setIsRecording(true);
    isSessionActiveRef.current = true;
    try {
      // Ensure websocket is connected before capturing audio, otherwise chunks are dropped.
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setStatus("Reconnecting WS...");
        connectWS();
        const connected = await ensureWSOpen(12000);
        if (!connected || !isStartingRef.current) {
          setStatus(connected ? "Online" : "WS Not Connected");
          if (!connected) console.error("WebSocket not connected; recording aborted");
          setIsRecording(false);
          isStartingRef.current = false;
          return;
        }
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          noiseSuppression: true,
          echoCancellation: true,
          autoGainControl: true,
        }
      });
      if (!isStartingRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      streamRef.current = stream;
      
      const ws = wsRef.current;
      if (!ws || ws.readyState !== 1) {
        console.log("WS not ready, aborting mic start");
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        setIsRecording(false);
        isStartingRef.current = false;
        return;
      }

      setStatus("Listening...");
      console.log("Mic started");
      console.log("Mic stream active:", stream.active);
      
      let audioContext = audioContextRef.current;
      if (!audioContext || audioContext.state === "closed") {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        audioContextRef.current = audioContext;
        workletLoadedRef.current = false;
      }

      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }
      console.log("AudioContext running");

      const triggerProcessing = () => {
        // Guards
        if (!isSessionActiveRef.current) return;
        
        console.log('triggerProcessing called, current state:', currentStateRef.current, 'capturing:', isCapturingRef.current);
        
        if (!isCapturingRef.current) {
          console.log('triggerProcessing aborted: not capturing.');
          return;
        }
        
        if (currentStateRef.current !== STATE.LISTENING) {
          console.log('triggerProcessing aborted: state is not LISTENING.');
          return;
        }

        if (
          currentStateRef.current === STATE.LISTENING &&
          !isListeningPaused
        ) {
          console.log("processing started");
          isProcessingRef.current = true; // Engage lock

          if (silenceIntervalRef.current) {
            clearInterval(silenceIntervalRef.current);
            silenceIntervalRef.current = null;
          }

          changeState(STATE.PROCESSING);
          stopPcmCaptureAndSend();
          sendControlMessage({ type: 'turn_end' });
        }
      };

      try {
        if (!workletLoadedRef.current) {
          await audioContext.audioWorklet.addModule('/vad-processor.js');
          workletLoadedRef.current = true;
        }
        console.log("VAD initialized");

        setupPcmCapture();
        
        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        
        processor.onaudioprocess = (e) => {
          const outputData = e.outputBuffer.getChannelData(0);
          for (let i = 0; i < outputData.length; i++) {
            outputData[i] = 0;
          }

          if (!isSessionActiveRef.current || !isCapturingRef.current || isListeningPaused) return;
          
          const inputData = e.inputBuffer.getChannelData(0);
          // Convert Float32 [-1, 1] to Int16 [-32768, 32767]
          const int16Data = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            let s = Math.max(-1, Math.min(1, inputData[i]));
            int16Data[i] = s < 0 ? s * 32768 : s * 32767;
          }
          
          // Only append if we are capturing
          pcmBuffersRef.current.push(int16Data);
        };

        const vadNode = new AudioWorkletNode(audioContext, 'vad-processor');
        audioSourceRef.current = source;
        vadNodeRef.current = vadNode;
        captureNodeRef.current = processor;

        source.connect(processor);
        processor.connect(audioContext.destination);

        // Immediately push the active sensitivity config downward
        vadNode.port.postMessage({ type: 'config', sensitivity: vadSensitivity });

        vadNode.port.onmessage = (event) => {
          if (!isSessionActiveRef.current) return;
          if (isProcessingRef.current) return; // THE PROCESSING LOCK
          const payload = event.data;
          if (!payload || !payload.type) return;

          if (payload.type === 'audio_level') {
            const level = Math.max(0, Math.min(1, Number(payload.value) || 0));
            setMicLevel(level);

            if (level > 0.05) {
              lastSpeechTimeRef.current = Date.now();
            }

            const now = Date.now();
            if (now - lastAudioLevelSendTsRef.current >= 150) {
              lastAudioLevelSendTsRef.current = now;
            }
            return;
          }
          if (payload.type === 'speech_start') {
            if (!isSessionActiveRef.current) return;
            lastSpeechTimeRef.current = Date.now();

            // STATE AWARE INTERRUPTION: Only kill audio if actually speaking!
            if (currentStateRef.current !== STATE.RESPONDING) return;
            
            console.log("speech detected - TRIGGERING BARGE-IN");

            lastSequenceIdRef.current += 1;
            
            // 1. Immediately halt all WebAudio sources
            if (pcmPlayerRef.current) {
                pcmPlayerRef.current.stopAll();
            }

            setStatus("Interrupted");
            
            // 4. Send exact Kill-Signal matching Enforcements
            sendControlMessage({ 
                type: "interrupt", 
                timestamp: Date.now(), 
                new_sequence_id: lastSequenceIdRef.current 
            });

            // 5. Force state back to listening immediately
            changeState(STATE.LISTENING);
            
            // 6. Rearm Mic: clears buffer for fresh new utterance
            setupPcmCapture();
          }

          if (payload.type === 'speech_end') {
            if (!isSessionActiveRef.current) return;
            console.log("end_of_speech triggered via VAD");
            triggerProcessing();
          }
        };

        source.connect(vadNode);
        vadNode.connect(audioContext.destination);

        // AEC WARMUP (CRITICAL): Give hardware chips time to construct inverse-phase echo maps
        console.log("AEC Warmup sequence initiated (600ms)...");
        await new Promise(r => setTimeout(r, 600));

        lastSpeechTimeRef.current = Date.now();
      } catch (vadError) {
        console.error("VAD Init Failed:", vadError);
      }

      isStartingRef.current = false;

      // Silence detection is now handled by VADWorklet's speech_end event.

    } catch (err) {
      console.error("Mic Setup Error:", err); setIsRecording(false);
      isStartingRef.current = false;
      // Fallback if VAD fails but mic works? 
      // Nah, if getUserMedia fails everything fails.
      setStatus("Mic Error");
    }
  };

  const stopRecording = () => {
    isSessionActiveRef.current = false;
    isStartingRef.current = false;
    isCapturingRef.current = false; // Prevent residual sample accumulation

    try {
      if (silenceIntervalRef.current) {
          clearInterval(silenceIntervalRef.current);
          silenceIntervalRef.current = null;
      }
      
      stopPcmCaptureAndSend();

      if (captureNodeRef.current) {
        try {
          captureNodeRef.current.disconnect();
        } catch (e) {}
        captureNodeRef.current = null;
      }

      if (vadNodeRef.current) {
        try { 
            vadNodeRef.current.port.close();
            vadNodeRef.current.disconnect(); 
        } catch (e) {}
        vadNodeRef.current = null;
      }
      if (audioSourceRef.current) {
        try { audioSourceRef.current.disconnect(); } catch (e) {}
        audioSourceRef.current = null;
      }

      // --- MANUAL STOP IS AN ABSOLUTE KILL SWITCH ---
      console.log('Absolute Kill Switch Triggered');
      
      // Stop actively speaking audio using the new PCMPlayer!
      if (pcmPlayerRef.current) {
        pcmPlayerRef.current.stopAll();
      }
      
      setIsRecording(false);
      changeState(STATE.IDLE);
      sendControlMessage({ type: 'abort' });

      if (audioContextRef.current && audioContextRef.current.state === 'running') {
        audioContextRef.current.suspend().catch(console.error);
      }
    } catch (e) {
      console.error("Critical error during stop sequence", e);
    } finally {
      if (streamRef.current) {
        try {
            streamRef.current.getTracks().forEach(track => track.stop());
        } catch (e) {}
        streamRef.current = null;
      }
    }
  };

  const pauseListening = () => {
    if (!isRecording) return;
    setIsListeningPaused(true);
  };

  const resumeListening = () => {
    if (!isRecording) return;
    setIsListeningPaused(false);
  };

  const onInterruptionProfileChange = (event) => {
    const profile = event.target.value;
    setInterruptionProfile(profile);
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    
    // Guard against sending while processing
    if (currentStateRef.current === STATE.PROCESSING || currentStateRef.current === STATE.RESPONDING || currentStateRef.current === STATE.THINKING) return;
    
    const textMsg = inputText.trim();
    
    // 1. Add to UI immediately
    setMessages(prev => [...prev, { role: 'user', content: textMsg }]);
    setInputText('');
    changeState(STATE.PROCESSING);
    
    // 2. Ensure WS is open
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connectWS();
      // Need to wait slightly for connect
      setTimeout(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          sendControlMessage({ type: 'text_input', text: textMsg });
        } else {
          setMessages(prev => [...prev, { role: 'assistant', content: "Connection error. Please try again." }]);
          changeState(STATE.IDLE);
        }
      }, 500);
      return;
    }

    // 3. Send text input
    sendControlMessage({ type: 'text_input', text: textMsg });
  };

  // Clean message content - remove raw JSON tool calls from display
  const cleanMessage = (text) => {
    if (!text) return '';
    // Remove raw JSON tool call blocks from display
    return text.replace(/\{"action".*?\}/gs, '').trim();
  };

  return (
    <JarvisOrb 
      ref={orbRef} 
      messages={messages}
      inputText={inputText}
      setInputText={setInputText}
      handleTextSubmit={handleTextSubmit}
      isRecording={isRecording}
      startRecording={startRecording}
      stopRecording={stopRecording}
      astaState={currentState}
      astaStatus={status}
    />
  );
}

export default App;

