import axios from 'axios';

// Centralized API configuration (CSP-compliant)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

console.log('API URL:', API_BASE_URL);

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    ...(import.meta.env.VITE_ASTA_API_TOKEN && {
      Authorization: `Bearer ${import.meta.env.VITE_ASTA_API_TOKEN}`,
    }),
    ...(import.meta.env.VITE_ASTA_DEVICE_ID && {
      'X-Device-Id': import.meta.env.VITE_ASTA_DEVICE_ID,
    }),
  },
});

// Response interceptor for error handling
api.interceptors.response.use(
  response => {
    return response;
  },
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
  // Using .webm as extension, browser specific but common
  formData.append('file', audioBlob, 'recording.webm');
  
  // Do NOT set Content-Type header manually for FormData
  const response = await api.post('/voice', formData);
  return response.data;
};
