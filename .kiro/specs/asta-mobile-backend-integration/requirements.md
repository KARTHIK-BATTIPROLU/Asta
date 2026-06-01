# Requirements Document

## Introduction

This document specifies the requirements for integrating the existing ASTA MOBILE Android application with the production-ready ASTA backend. The ASTA backend is a comprehensive AI-powered personal assistant system featuring 6 specialized workflow graphs, 5-layer memory architecture, 7 supporting services, RESTful API with JWT authentication, and real-time WebSocket support. The Android app currently has basic structure with text-based chat functionality but requires significant enhancements to fully integrate with the backend's capabilities, including wake word detection, WebSocket communication, audio streaming, and a Flutter-based Jarvis orb UI.

## Glossary

- **ASTA_Backend**: The production-ready FastAPI server with LangGraph workflows, memory layers, and services
- **ASTA_Mobile**: The Android application (minSdk 26, targetSdk 36) that connects to ASTA_Backend
- **Wake_Word_Service**: Android service using Picovoice Porcupine for "Hey Jarvis" detection
- **Foreground_Service**: ASTAForegroundService - always-running Android service managing wake word detection
- **WebSocket_Client**: ASTAWebSocketClient - manages bidirectional real-time communication with ASTA_Backend
- **Audio_Streamer**: Component handling audio recording (16kHz PCM) and playback (24kHz PCM)
- **Jarvis_Orb**: Flutter UI component displaying animated blue orb with states (Idle, Listening, Speaking)
- **Session**: A conversation context maintained by ASTA_Backend's memory layer
- **Workflow**: One of 6 backend graphs (routine, research, linkedin, youtube, instagram, habit)
- **JWT_Token**: JSON Web Token for authenticating requests to ASTA_Backend
- **Stage_Feed**: Real-time workflow stage updates broadcast via WebSocket
- **Deepgram**: Third-party service providing STT (Speech-to-Text) and TTS (Text-to-Speech) via WebSocket
- **Method_Channel**: Flutter-Kotlin communication bridge for triggering actions
- **Event_Channel**: Flutter-Kotlin communication bridge for streaming events

## Requirements

### Requirement 1: Backend Connection Configuration

**User Story:** As a developer, I want the Android app to connect to the production ASTA backend, so that users can access all backend features.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL replace the hardcoded ngrok URL with a configurable production backend URL
2. THE ASTA_Mobile SHALL support both HTTP and HTTPS protocols for backend communication
3. THE ASTA_Mobile SHALL validate the backend URL format before attempting connection
4. WHEN the backend URL is invalid, THE ASTA_Mobile SHALL display an error message to the user
5. THE ASTA_Mobile SHALL persist the backend URL configuration across app restarts

### Requirement 2: JWT Authentication

**User Story:** As a user, I want secure authentication with the backend, so that my data and sessions are protected.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL include a JWT_Token in the Authorization header for all API requests
2. THE ASTA_Mobile SHALL include the JWT_Token as a query parameter when establishing WebSocket connections
3. WHEN the JWT_Token is missing or invalid, THE ASTA_Backend SHALL return a 401 Unauthorized response
4. WHEN receiving a 401 response, THE ASTA_Mobile SHALL notify the user of authentication failure
5. THE ASTA_Mobile SHALL securely store the JWT_Token using Android's EncryptedSharedPreferences

### Requirement 3: Session Management

**User Story:** As a user, I want my conversations to maintain context, so that ASTA remembers our discussion.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL generate a unique Session identifier for each conversation
2. THE ASTA_Mobile SHALL include the Session identifier in all chat requests to ASTA_Backend
3. THE ASTA_Backend SHALL persist conversation context across multiple requests within the same Session
4. THE ASTA_Mobile SHALL maintain the same Session identifier until the user explicitly starts a new conversation
5. WHEN a Session expires on the backend, THE ASTA_Mobile SHALL generate a new Session identifier for subsequent requests

### Requirement 4: Workflow Routing

**User Story:** As a user, I want ASTA to route my requests to the appropriate workflow, so that I get specialized responses.

#### Acceptance Criteria

1. THE ASTA_Backend SHALL classify user intent and route requests to one of 6 Workflow graphs
2. THE ASTA_Mobile SHALL support sending workflow hints in chat requests to ASTA_Backend
3. THE ASTA_Backend SHALL return the selected Workflow name in chat responses
4. THE ASTA_Mobile SHALL display the active Workflow name to the user
5. FOR ALL 6 Workflow types (routine, research, linkedin, youtube, instagram, habit), THE ASTA_Backend SHALL process requests and return valid responses

### Requirement 5: Wake Word Detection Service

**User Story:** As a user, I want to activate ASTA by saying "Hey Jarvis", so that I can use hands-free voice interaction.

#### Acceptance Criteria

1. THE Wake_Word_Service SHALL use Picovoice Porcupine SDK version 3.0.0 or higher for wake word detection
2. THE Wake_Word_Service SHALL detect the wake word "Hey Jarvis" with a false positive rate below 1 per hour
3. WHEN the wake word is detected, THE Wake_Word_Service SHALL trigger the voice session activity
4. THE Wake_Word_Service SHALL continuously monitor audio input at 16000 Hz sample rate
5. THE Wake_Word_Service SHALL consume less than 5% CPU on average during idle monitoring
6. WHEN audio recording permission is denied, THE Wake_Word_Service SHALL stop and notify the user

### Requirement 6: Foreground Service Management

**User Story:** As a user, I want ASTA to always be listening for the wake word, so that I can activate it anytime.

#### Acceptance Criteria

1. THE Foreground_Service SHALL display a persistent notification with text "ASTA Online - Say 'Hey Jarvis' to wake me up"
2. THE Foreground_Service SHALL start the Wake_Word_Service when the Foreground_Service starts
3. THE Foreground_Service SHALL stop the Wake_Word_Service when the Foreground_Service stops
4. WHEN the system kills the Foreground_Service, THE Android system SHALL automatically restart it using START_STICKY
5. THE Foreground_Service SHALL provide a LocalBinder for MainActivity to bind and control the service
6. THE Foreground_Service SHALL declare foregroundServiceType as "microphone" in AndroidManifest

### Requirement 7: WebSocket Connection Management

**User Story:** As a user, I want real-time communication with ASTA, so that I get immediate responses and updates.

#### Acceptance Criteria

1. THE WebSocket_Client SHALL establish a WebSocket connection to wss://[backend-url]/voice/ws?token=[JWT_Token]
2. WHEN the WebSocket connection is established, THE ASTA_Backend SHALL send a "connected" message
3. WHEN the WebSocket connection fails, THE WebSocket_Client SHALL attempt to reconnect with exponential backoff up to 5 times
4. THE WebSocket_Client SHALL send ping messages every 30 seconds to maintain the connection
5. WHEN a pong response is not received within 10 seconds, THE WebSocket_Client SHALL close and reconnect
6. THE WebSocket_Client SHALL handle network changes and reconnect automatically when connectivity is restored

### Requirement 8: WebSocket Message Handling

**User Story:** As a developer, I want to handle all WebSocket message types, so that the app responds correctly to backend events.

#### Acceptance Criteria

1. WHEN receiving a "transcript" message, THE ASTA_Mobile SHALL display the transcribed text in the UI
2. WHEN receiving a "response" message, THE ASTA_Mobile SHALL display ASTA's text response in the UI
3. WHEN receiving an "audio" message with base64-encoded PCM data, THE ASTA_Mobile SHALL decode and play the audio
4. WHEN receiving a "stage" message, THE ASTA_Mobile SHALL update the Stage_Feed display with the workflow stage name
5. WHEN receiving an "error" message, THE ASTA_Mobile SHALL display the error to the user and log it for debugging
6. WHEN receiving a "connected" message, THE ASTA_Mobile SHALL update the connection status indicator

### Requirement 9: Audio Recording and Streaming

**User Story:** As a user, I want to speak to ASTA naturally, so that I can have voice conversations.

#### Acceptance Criteria

1. THE Audio_Streamer SHALL record audio at 16000 Hz sample rate with PCM 16-bit encoding in mono channel
2. WHEN recording starts, THE Audio_Streamer SHALL stream audio chunks to ASTA_Backend via WebSocket in real-time
3. THE Audio_Streamer SHALL use a buffer size that balances latency (below 500ms) and stability
4. WHEN recording stops, THE Audio_Streamer SHALL send a final audio chunk and stop streaming
5. THE Audio_Streamer SHALL release audio recording resources when not in use
6. WHEN audio recording fails, THE Audio_Streamer SHALL notify the user and log the error

### Requirement 10: Audio Playback

**User Story:** As a user, I want to hear ASTA's voice responses, so that I can have natural conversations.

#### Acceptance Criteria

1. THE Audio_Streamer SHALL play received PCM audio at 24000 Hz sample rate with 16-bit encoding
2. WHEN audio data is received via WebSocket, THE Audio_Streamer SHALL queue it for playback
3. THE Audio_Streamer SHALL play audio chunks in the order received without gaps or overlaps
4. WHEN playback completes, THE Audio_Streamer SHALL notify the application to resume listening
5. THE Audio_Streamer SHALL release audio playback resources when not in use
6. WHEN audio playback fails, THE Audio_Streamer SHALL notify the user and log the error

### Requirement 11: Jarvis Orb Visual States

**User Story:** As a user, I want visual feedback on ASTA's state, so that I know when to speak and when ASTA is responding.

#### Acceptance Criteria

1. WHEN ASTA is idle, THE Jarvis_Orb SHALL display a gentle pulsing blue orb with text "TAP TO TALK"
2. WHEN ASTA is listening, THE Jarvis_Orb SHALL display an active pulsing blue orb with text "LISTENING"
3. WHEN ASTA is speaking, THE Jarvis_Orb SHALL display wave rings emanating from the orb with text "SPEAKING"
4. THE Jarvis_Orb SHALL animate state transitions smoothly at 60 frames per second
5. THE Jarvis_Orb SHALL use a blue color palette (primary: #1E88E5, accent: #4FC3F7, background: #050A18)

### Requirement 12: Jarvis Orb User Interaction

**User Story:** As a user, I want to tap the orb to start talking, so that I can initiate conversations manually.

#### Acceptance Criteria

1. WHEN the user taps the Jarvis_Orb in idle state, THE ASTA_Mobile SHALL start audio recording and transition to listening state
2. WHEN the user taps the Jarvis_Orb in listening state, THE ASTA_Mobile SHALL stop audio recording and send the audio to ASTA_Backend
3. THE Jarvis_Orb SHALL provide haptic feedback when tapped
4. THE Jarvis_Orb SHALL be tappable with a minimum touch target size of 110 pixels radius
5. WHEN ASTA is speaking, THE Jarvis_Orb SHALL ignore tap events until speaking completes

### Requirement 13: Transcript and Response Display

**User Story:** As a user, I want to see what I said and ASTA's response, so that I can review our conversation.

#### Acceptance Criteria

1. THE Jarvis_Orb screen SHALL display the user's transcribed speech below the orb
2. THE Jarvis_Orb screen SHALL display ASTA's text response below the transcript
3. THE Jarvis_Orb screen SHALL display the Stage_Feed showing current workflow stage below the response
4. WHEN a new transcript is received, THE ASTA_Mobile SHALL replace the previous transcript text
5. WHEN a new response is received, THE ASTA_Mobile SHALL replace the previous response text
6. THE transcript, response, and Stage_Feed text SHALL be readable with minimum font size of 14sp

### Requirement 14: Flutter-Kotlin Method Channel

**User Story:** As a developer, I want Flutter UI to trigger Kotlin actions, so that the UI can control voice sessions.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL create a Method_Channel named "com.asta/voice"
2. WHEN Flutter calls "startListening" method, THE ASTA_Mobile SHALL start the Audio_Streamer and WebSocket_Client
3. WHEN Flutter calls "stopListening" method, THE ASTA_Mobile SHALL stop the Audio_Streamer
4. WHEN Flutter calls "sendText" method with a message parameter, THE ASTA_Mobile SHALL send the text to ASTA_Backend via WebSocket
5. THE Method_Channel SHALL return success or error results to Flutter for all method calls

### Requirement 15: Flutter-Kotlin Event Channel

**User Story:** As a developer, I want Kotlin to stream events to Flutter UI, so that the UI updates in real-time.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL create an Event_Channel named "com.asta/events"
2. WHEN a WebSocket message is received, THE ASTA_Mobile SHALL send the message type and data to Flutter via Event_Channel
3. THE Event_Channel SHALL support streaming events for types: connected, transcript, response, audio, stage, error
4. WHEN the WebSocket connection state changes, THE ASTA_Mobile SHALL send a connection status event to Flutter
5. THE Event_Channel SHALL handle Flutter listener lifecycle (onListen, onCancel) correctly

### Requirement 16: MainActivity Initialization

**User Story:** As a user, I want the app to initialize properly on launch, so that all features are ready to use.

#### Acceptance Criteria

1. WHEN the app launches, THE MainActivity SHALL initialize the Flutter engine
2. WHEN the app launches, THE MainActivity SHALL request RECORD_AUDIO permission if not granted
3. WHEN RECORD_AUDIO permission is granted, THE MainActivity SHALL start the Foreground_Service
4. WHEN RECORD_AUDIO permission is denied, THE MainActivity SHALL display a rationale and disable voice features
5. THE MainActivity SHALL bind to the Foreground_Service to receive wake word detection callbacks
6. THE MainActivity SHALL set up the Method_Channel and Event_Channel before displaying the Flutter UI

### Requirement 17: Wake Word Callback Handling

**User Story:** As a user, I want the app to open when I say "Hey Jarvis", so that I can start talking immediately.

#### Acceptance Criteria

1. WHEN the Wake_Word_Service detects "Hey Jarvis", THE Foreground_Service SHALL notify the MainActivity via callback
2. WHEN MainActivity receives the wake word callback, THE MainActivity SHALL launch the Jarvis_Orb screen
3. WHEN the Jarvis_Orb screen launches, THE ASTA_Mobile SHALL play a wake prompt "Yes, how can I help?"
4. WHEN the wake prompt completes, THE ASTA_Mobile SHALL automatically start listening for user speech
5. WHEN the screen is off, THE MainActivity SHALL turn on the screen and show the Jarvis_Orb screen over the lock screen

### Requirement 18: Voice Session Lifecycle

**User Story:** As a user, I want voice sessions to flow naturally, so that conversations feel seamless.

#### Acceptance Criteria

1. WHEN a voice session starts, THE ASTA_Mobile SHALL transition through states: Idle → Speaking (prompt) → Listening → Processing → Speaking (response) → Idle
2. WHEN the user stops speaking for 2 seconds during listening, THE ASTA_Mobile SHALL automatically stop recording and send audio to ASTA_Backend
3. WHEN ASTA's response audio completes playback, THE ASTA_Mobile SHALL return to idle state and close the Jarvis_Orb screen
4. WHEN the user presses back button during a voice session, THE ASTA_Mobile SHALL cancel the session and return to idle
5. WHEN no user speech is detected within 7 seconds of listening start, THE ASTA_Mobile SHALL timeout and return to idle

### Requirement 19: Error Handling and Recovery

**User Story:** As a user, I want the app to handle errors gracefully, so that I can continue using ASTA even when issues occur.

#### Acceptance Criteria

1. WHEN the WebSocket connection fails, THE ASTA_Mobile SHALL display "Connection lost, retrying..." and attempt reconnection
2. WHEN the ASTA_Backend returns an error response, THE ASTA_Mobile SHALL display the error message to the user
3. WHEN audio recording fails, THE ASTA_Mobile SHALL display "Microphone error" and return to idle state
4. WHEN audio playback fails, THE ASTA_Mobile SHALL display "Audio playback error" and return to idle state
5. WHEN the Foreground_Service crashes, THE Android system SHALL restart it automatically within 5 seconds
6. FOR ALL errors, THE ASTA_Mobile SHALL log detailed error information for debugging

### Requirement 20: Battery and Performance Optimization

**User Story:** As a user, I want ASTA to run efficiently, so that my battery lasts throughout the day.

#### Acceptance Criteria

1. THE Wake_Word_Service SHALL consume less than 5% CPU on average during idle monitoring
2. THE Foreground_Service SHALL consume less than 50MB of RAM during normal operation
3. THE ASTA_Mobile SHALL release audio resources (recorder, player) immediately when not in use
4. THE WebSocket_Client SHALL close idle connections after 5 minutes of inactivity
5. THE ASTA_Mobile SHALL use Android's Doze mode exemptions only for the Foreground_Service
6. THE Jarvis_Orb animations SHALL maintain 60 FPS without causing frame drops or jank

### Requirement 21: Permissions and Security

**User Story:** As a user, I want my privacy protected, so that I trust ASTA with my voice data.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL declare RECORD_AUDIO, INTERNET, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE, and WAKE_LOCK permissions in AndroidManifest
2. THE ASTA_Mobile SHALL request RECORD_AUDIO permission at runtime before starting voice features
3. THE ASTA_Mobile SHALL store the JWT_Token using Android's EncryptedSharedPreferences with AES-256 encryption
4. THE ASTA_Mobile SHALL use HTTPS (wss://) for all production backend connections
5. THE ASTA_Mobile SHALL not log sensitive data (JWT_Token, audio data) in production builds
6. THE ASTA_Mobile SHALL clear audio buffers immediately after transmission to ASTA_Backend

### Requirement 22: Build Configuration and Dependencies

**User Story:** As a developer, I want all dependencies properly configured, so that the app builds successfully.

#### Acceptance Criteria

1. THE ASTA_Mobile build.gradle SHALL include OkHttp version 4.12.0 or higher for WebSocket support
2. THE ASTA_Mobile build.gradle SHALL include Picovoice Porcupine Android SDK version 3.0.0 or higher
3. THE ASTA_Mobile build.gradle SHALL include Flutter module as a local dependency
4. THE ASTA_Mobile build.gradle SHALL set minSdk to 26 and targetSdk to 36
5. THE ASTA_Mobile build.gradle SHALL enable Kotlin coroutines support
6. THE ASTA_Mobile SHALL compile without errors or warnings on Android Studio Hedgehog or later

### Requirement 23: Testing and Verification

**User Story:** As a developer, I want to verify all features work correctly, so that users have a reliable experience.

#### Acceptance Criteria

1. THE ASTA_Mobile SHALL successfully connect to the production ASTA_Backend and receive a "connected" message
2. THE Wake_Word_Service SHALL detect "Hey Jarvis" within 2 seconds of utterance completion
3. THE Audio_Streamer SHALL stream audio to ASTA_Backend with end-to-end latency below 1 second
4. THE ASTA_Backend SHALL return a valid response for all 6 Workflow types when invoked from ASTA_Mobile
5. THE Jarvis_Orb SHALL display all 3 states (Idle, Listening, Speaking) with smooth animations
6. THE ASTA_Mobile SHALL complete a full voice conversation (wake word → speech → response → idle) without crashes
7. THE Foreground_Service SHALL survive app force-stop and restart automatically within 10 seconds
