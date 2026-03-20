import React, { useState, useRef, useEffect } from 'react';
import { sendTextMessage, sendVoiceMessage } from './api';
import { Mic, Send, Bot, User, Loader2, StopCircle, Volume2, VolumeX } from 'lucide-react';
import './App.css';

function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi! I'm Asta. How can I help you today?" }
  ]);
  const [inputText, setInputText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;
    
    const userMsg = inputText;
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setInputText('');
    setLoading(true);

    try {
      const data = await sendTextMessage(userMsg, voiceEnabled);
      // Correcting property access from .response to .reply based on API structure
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply || "No response received." }]);
      
      if (data.audio_base64 && voiceEnabled) {
        playAudio(data.audio_base64);
      }
    } catch (error) {
      console.error("Error sending message:", error);
      setMessages(prev => [...prev, { role: 'assistant', content: "Sorry, something went wrong." }]);
    } finally {
      setLoading(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
        ? 'audio/webm;codecs=opus' 
        : 'audio/webm';
        
      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        await processVoiceMessage(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      // alert("Could not access microphone.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const processVoiceMessage = async (audioBlob) => {
    setLoading(true);
    const tempId = Date.now();
    setMessages(prev => [...prev, { role: 'user', content: "🎤 ...Processing Voice...", id: tempId, isTemp: true }]);
    
    try {
      const data = await sendVoiceMessage(audioBlob);
      
      setMessages(prev => {
        const filtered = prev.filter(m => !m.isTemp);
        const newMsgs = [...filtered];
        
        if (data.transcript) {
            newMsgs.push({ role: 'user', content: data.transcript });
        } else {
            newMsgs.push({ role: 'user', content: "🎤 (Audio Message)" });
        }
        
        // Correcting property access from .response to .reply based on API structure
        if (data.reply) {
            newMsgs.push({ role: 'assistant', content: data.reply });
        }
        
        return newMsgs;
      });

      if (data.audio_base64 && voiceEnabled) {
        playAudio(data.audio_base64);
      }
    } catch (error) {
      console.error("Voice processing error:", error);
      setMessages(prev => {
         const filtered = prev.filter(m => !m.isTemp);
         return [...filtered, { role: 'assistant', content: "Sorry, I couldn't process that audio." }];
      });
    } finally {
      setLoading(false);
    }
  };

  const playAudio = (base64String) => {
    try {
        const audioUrl = `data:audio/mp3;base64,${base64String}`;
        const audio = new Audio(audioUrl);
        audio.play().catch(e => console.error("Playback failed:", e));
    } catch (e) {
        console.error("Audio setup failed:", e);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>ASTA</h1>
        <div className="controls">
            <button 
                className="icon-button"
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                title={voiceEnabled ? "Mute Voice" : "Enable Voice"}
                type="button"
            >
                {voiceEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
            </button>
            <div className="status-dot"></div>
        </div>
      </header>

      <div className="chat-window">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role} ${msg.isTemp ? 'temp' : ''}`}>
            <div className="avatar">
              {msg.role === 'assistant' ? <Bot size={20} /> : <User size={20} />}
            </div>
            <div className="bubble">
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="avatar"><Bot size={20} /></div>
            <div className="bubble loading">
              <Loader2 className="spinner" size={16} /> Thinking...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <button 
          className={`mic-button ${isRecording ? 'recording' : ''}`}
          onClick={isRecording ? stopRecording : startRecording}
          title={isRecording ? "Stop Recording" : "Start Recording"}
          type="button"
        >
          {isRecording ? <StopCircle size={24} /> : <Mic size={24} />}
        </button>
        
        <input 
          id="chat-input"
          name="chat-input"
          type="text" 
          placeholder="Type a message..." 
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          disabled={isRecording || loading}
          autoComplete="off"
        />
        
        <button 
          className="send-button"
          onClick={handleSendMessage}
          disabled={!inputText.trim() || loading || isRecording}
          title="Send Message"
          type="button"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
}

export default App;
