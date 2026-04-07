class VADProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // VAD Timing Parameters
    // 128 samples at 16000Hz = 8ms per process() frame
    this.minSpeechFrames = 6;  // ~48ms (Speech Start Hysteresis)
    this.minSilenceFrames = 312; // 2500ms (Speech End Hysteresis)

    this.speechFrames = 0;
    this.silenceFrames = 0;
    this.isSpeaking = false;
    this.levelFrameCounter = 0;
    
    // Dynamic AGC (Auto-Gain Control) / Noise Gate
    this.silenceBufferSize = 625; // ~5 seconds of silence history at 8ms/frame
    this.silenceBuffer = new Float32Array(this.silenceBufferSize);
    this.silenceBufferIndex = 0;
    this.silenceBufferFilled = false;
    this.currentSilenceAvgMatch = 0.005; // Starting generic noise floor

    // Sensitivity Parameter (controlled by React UI config)
    this.sensitivityMultiplier = 4.0;

    // Listen to UI config changes
    this.port.onmessage = (event) => {
      const data = event.data;
      if (data && data.type === 'config') {
         if (data.sensitivity) {
           this.sensitivityMultiplier = data.sensitivity;
         }
      } else if (data && data.type === 'reset') {
         this.isSpeaking = false;
         this.speechFrames = 0;
         this.silenceFrames = 0;
      }
    };
  }

  calculateRMS(input) {
    let sum = 0;
    for (let i = 0; i < input.length; i++) {
       sum += input[i] * input[i];
    }
    return Math.sqrt(sum / input.length);
  }

  updateNoiseFloor(rms) {
    this.silenceBuffer[this.silenceBufferIndex] = rms;
    this.silenceBufferIndex++;
    if (this.silenceBufferIndex >= this.silenceBufferSize) {
      this.silenceBufferIndex = 0;
      this.silenceBufferFilled = true;
    }

    // Only recalculate strictly occasionally to save CPU cycles (e.g. every 10 frames)
    if (this.silenceBufferIndex % 10 === 0) {
      let limit = this.silenceBufferFilled ? this.silenceBufferSize : this.silenceBufferIndex;
      let sum = 0;
      for (let i = 0; i < limit; i++) {
         sum += this.silenceBuffer[i];
      }
      this.currentSilenceAvgMatch = limit > 0 ? (sum / limit) : 0.005;
    }
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    
    const channelData = input[0];
    const rms = this.calculateRMS(channelData);
    const db = 20 * Math.log10(rms + 1e-8);
    const normalizedLevel = Math.max(0, Math.min(1, (db + 60) / 60));

    this.levelFrameCounter += 1;
    if (this.levelFrameCounter >= 3) {
      this.levelFrameCounter = 0;
      this.port.postMessage({ type: 'audio_level', value: normalizedLevel, db });
    }

    // Dynamic Gate Calculation
    // We floor the ambient RMS to a minimum of 0.001 to prevent floating point dead zeros
    const activeThreshold = Math.max(0.001, this.currentSilenceAvgMatch) * this.sensitivityMultiplier;

    // VAD Logic
    if (rms > activeThreshold) {
        this.speechFrames++;
        this.silenceFrames = 0;

        if (!this.isSpeaking && this.speechFrames >= this.minSpeechFrames) {
            this.isSpeaking = true;
            this.port.postMessage({ type: 'speech_start' });
        }
    } else {
        if (this.isSpeaking) {
            this.silenceFrames++;
            if (this.silenceFrames >= this.minSilenceFrames) {
                this.isSpeaking = false;
                this.speechFrames = 0;
                this.port.postMessage({ type: 'speech_end' });
            }
        } else {
             this.speechFrames = 0;
             // Sample the noise floor exclusively when we are confident nobody is talking
             this.updateNoiseFloor(rms);
        }
    }

    return true;
  }
}

registerProcessor('vad-processor', VADProcessor);