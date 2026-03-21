import axios from 'axios';

// Use environment variable if available, otherwise default to relative path (for dev proxy)
const baseURL = import.meta.env.VITE_API_URL 
  ? `${import.meta.env.VITE_API_URL}/api` 
  : '/api';

const api = axios.create({
  baseURL: baseURL,
});

// Interceptor to debug responses
api.interceptors.response.use(
  response => {
    // console.log("API Response:", response.data);
    return response;
  },
  error => {
    console.error("API Error:", error);
    return Promise.reject(error);
  }
);

export const sendTextMessage = async (text, voiceEnabled = false) => {
  const response = await api.post('/chat', { 
    message: text,
    voice_enabled: voiceEnabled
  });
  return response.data;
};

export const sendVoiceMessage = async (audioBlob) => {
  const formData = new FormData();
  // Using .webm as extension, browser specific but common
  formData.append('file', audioBlob, 'recording.webm');
  
  // Do NOT set Content-Type header manually for FormData
  const response = await api.post('/voice', formData);
  return response.data;
};
