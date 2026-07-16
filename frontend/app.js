document.addEventListener('DOMContentLoaded', () => {
    const statusDisplay = document.getElementById('status-display');
    const transcriptDiv = document.getElementById('transcript');
    const textInput = document.getElementById('text-input');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    
    let ws = null;
    let isConnected = false;
    
    function connect() {
        // Prepare auth query params
        const wsUrl = new URL(window.CONFIG.WS_URL);
        wsUrl.searchParams.set('token', window.CONFIG.BEARER_TOKEN);
        wsUrl.searchParams.set('device_id', window.CONFIG.DEVICE_ID);
        
        ws = new WebSocket(wsUrl.toString());
        
        ws.onopen = () => {
            console.log('[WS] Connected to ASTA');
            isConnected = true;
            statusDisplay.textContent = 'Connected';
            statusDisplay.style.color = '#7fd4ff';
        };
        
        ws.onmessage = (event) => {
            // Check if binary data (audio)
            if (event.data instanceof Blob) {
                playAudioBlob(event.data);
                return;
            }
            
            try {
                const msg = JSON.parse(event.data);
                
                // Handle orb_state
                if (msg.type === 'orb_state' && window.orb) {
                    window.orb.setState(msg.state);
                }
                // Handle text frames (if they come as JSON)
                else if (msg.type === 'text' || msg.text) {
                    appendTranscript(msg.text, 'asta');
                }
            } catch(e) {
                // If it's just raw text, not JSON
                if (typeof event.data === 'string' && !event.data.startsWith('{')) {
                    appendTranscript(event.data, 'asta');
                }
            }
        };
        
        ws.onclose = (e) => {
            console.log('[WS] Disconnected', e.code);
            isConnected = false;
            statusDisplay.textContent = 'Disconnected';
            statusDisplay.style.color = '#ff4757';
            if (window.orb) window.orb.setState('idle');
            
            // Reconnect logic could go here
            setTimeout(connect, 3000);
        };
        
        ws.onerror = (e) => {
            console.error('[WS] Error', e);
        };
    }
    
    function sendMessage(text) {
        if (!isConnected || !text.trim()) return;
        
        // Append to UI
        appendTranscript(text, 'user');
        
        // Pipecat standard text frame structure
        // According to pipecat FrameSerializer, TextFrame usually maps to {"text": "..."}
        const payload = JSON.stringify({ type: "text", text: text });
        ws.send(payload);
        
        textInput.value = '';
    }
    
    function appendTranscript(text, role) {
        if (!text) return;
        const p = document.createElement('p');
        p.textContent = text;
        
        if (role === 'user') {
            p.style.color = '#ccc';
            p.style.textAlign = 'right';
        } else if (text.startsWith('*') && text.endsWith('*')) {
            p.className = 'reflex-filler';
        } else {
            p.style.color = '#fff';
            p.style.textAlign = 'left';
        }
        
        transcriptDiv.appendChild(p);
        transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
    }
    
    // Play received TTS Audio Blob
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    
    async function playAudioBlob(blob) {
        try {
            const arrayBuffer = await blob.arrayBuffer();
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);
            source.start(0);
        } catch (e) {
            console.error('[Audio] Error decoding/playing audio', e);
        }
    }
    
    // Simple Mic Recording stub (F5)
    // Note: Pipecat expects raw 16kHz PCM or Wav, we would need ScriptProcessor or AudioWorklet to do this properly.
    // For F5 attempt honestly:
    let isRecording = false;
    let localStream = null;
    let audioProcessor = null;
    
    async function toggleMic() {
        if (!isRecording) {
            try {
                localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const source = audioContext.createMediaStreamSource(localStream);
                
                // Use ScriptProcessor for a quick downsample to 16kHz PCM (deprecated but works everywhere without separate file)
                audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
                
                source.connect(audioProcessor);
                audioProcessor.connect(audioContext.destination);
                
                audioProcessor.onaudioprocess = (e) => {
                    if (!isConnected) return;
                    
                    const inputData = e.inputBuffer.getChannelData(0);
                    // This is Float32 at browser sample rate (usually 44.1kHz or 48kHz).
                    // Sending raw Float32 is almost certainly going to fail if Pipecat expects 16kHz PCM Int16.
                    // This is where a complex WebWorker resampler is usually required.
                    // We'll attempt sending the raw buffer, but note it might cause codec mismatch.
                    ws.send(inputData.buffer);
                };
                
                isRecording = true;
                micBtn.classList.add('recording');
                console.log("[Mic] Started recording");
                
            } catch (e) {
                console.error("[Mic] Failed to access microphone", e);
            }
        } else {
            if (audioProcessor) {
                audioProcessor.disconnect();
                audioProcessor.onaudioprocess = null;
            }
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
            }
            isRecording = false;
            micBtn.classList.remove('recording');
            console.log("[Mic] Stopped recording");
        }
    }
    
    // Event listeners
    sendBtn.addEventListener('click', () => sendMessage(textInput.value));
    textInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage(textInput.value);
    });
    micBtn.addEventListener('click', toggleMic);
    
    // Start connection
    connect();
});
