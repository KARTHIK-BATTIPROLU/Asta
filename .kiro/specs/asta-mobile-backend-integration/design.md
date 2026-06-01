# Design Document

## Introduction

This document specifies the technical design for integrating the existing ASTA MOBILE Android application with the production-ready ASTA backend. The design addresses all 23 requirements through a comprehensive architecture that enables seamless voice-first interaction, real-time communication, and robust error handling while maintaining optimal performance and security.

## System Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ASTA MOBILE APPLICATION                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │   Flutter UI    │    │  Kotlin Native  │                    │
│  │                 │    │                 │                    │
│  │ • Jarvis Orb    │◄──►│ • MainActivity   │                    │
│  │ • Stage Feed    │    │ • Services      │                    │
│  │ • Transcript    │    │ • Audio         │                    │
│  │ • Response      │    │ • WebSocket     │                    │
│  └─────────────────┘    └─────────────────┘                    │
│           │                       │                            │
│    Method/Event Channels          │                            │
│           │                       │                            │
├───────────┼───────────────────────┼────────────────────────────┤
│           │              ┌────────▼────────┐                   │
│           │              │ Foreground      │                   │
│           │              │ Service         │                   │
│           │              │                 │                   │
│           │              │ • Wake Word     │                   │
│           │              │ • Always-On     │                   │
│           │              │ • Notifications │                   │
│           │              └─────────────────┘                   │
└───────────┼─────────────────────────────────────────────────────┘
            │
    ┌───────▼───────┐
    │   WebSocket   │
    │  Connection   │
    │               │
    │ wss://backend │
    │ /voice/ws     │
    └───────┬───────┘
            │
┌───────────▼─────────────────────────────────────────────────────┐
│                    ASTA BACKEND                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │   Supervisor    │    │   6 Workflow    │                    │
│  │   LangGraph     │◄──►│   Graphs        │                    │
│  │                 │    │                 │                    │
│  │ • Intent Class  │    │ • Routine       │                    │
│  │ • Memory Fetch  │    │ • Research      │                    │
│  │ • Route Logic   │    │ • LinkedIn      │                    │
│  └─────────────────┘    │ • YouTube       │                    │
│                         │ • Instagram     │                    │
│                         │ • Habit         │                    │
│                         └─────────────────┘                    │
│                                  │                             │
│  ┌─────────────────┐    ┌────────▼────────┐                   │
│  │   Memory        │    │   Services      │                   │
│  │   Engine        │◄──►│                 │                   │
│  │                 │    │ • STT/TTS       │                   │
│  │ • Neo4j Graph   │    │ • Notion        │                   │
│  │ • Pinecone Vec  │    │ • Research      │                   │
│  │ • MongoDB Store │    │ • Weather       │                   │
│  └─────────────────┘    └─────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

1. **Wake Word Detection**: Porcupine SDK → WakeWordService → ForegroundService → MainActivity
2. **Voice Session**: MainActivity → Flutter UI → Method Channel → WebSocket Client
3. **Audio Streaming**: AudioStreamer → WebSocket → Backend STT Service
4. **Backend Processing**: Supervisor Graph → Workflow Selection → Memory Retrieval → Response Generation
5. **Response Delivery**: Backend TTS → WebSocket → AudioStreamer → Flutter UI Updates

## Component Design Specifications

### 1. Android Application Architecture

#### 1.1 MainActivity (Kotlin)

**Purpose**: Application entry point, permission management, service coordination

**Key Responsibilities**:
- Initialize Flutter engine and establish communication channels
- Request and manage RECORD_AUDIO permission
- Start/stop ASTAForegroundService based on permission status
- Handle wake word callbacks from foreground service
- Manage app lifecycle and screen wake functionality

**Design Pattern**: Single Activity Architecture with Flutter integration

**Key Methods**:
```kotlin
class MainActivity : FlutterActivity() {
    // Service binding and management
    private fun bindToForegroundService()
    private fun unbindFromForegroundService()
    
    // Permission handling
    private fun requestAudioPermission()
    private fun onPermissionResult(granted: Boolean)
    
    // Wake word callback handling
    private fun onWakeWordDetected()
    private fun launchJarvisScreen()
    
    // Method/Event channel setup
    private fun setupMethodChannel()
    private fun setupEventChannel()
}
```

#### 1.2 ASTAForegroundService (Kotlin)

**Purpose**: Always-running service for wake word detection and system integration

**Key Responsibilities**:
- Display persistent notification with wake status
- Manage WakeWordService lifecycle
- Provide LocalBinder for MainActivity communication
- Handle service restart scenarios (START_STICKY)
- Maintain wake word detection state

**Service Type**: Foreground Service with MICROPHONE type

**Key Methods**:
```kotlin
class ASTAForegroundService : Service() {
    // Service lifecycle
    override fun onStartCommand(): Int
    override fun onBind(): IBinder
    
    // Wake word service management
    private fun startWakeWordService()
    private fun stopWakeWordService()
    
    // Notification management
    private fun createNotificationChannel()
    private fun updateNotification(status: String)
    
    // Callback interface
    interface WakeWordCallback {
        fun onWakeWordDetected()
    }
}
```

#### 1.3 WakeWordService (Kotlin)

**Purpose**: Picovoice Porcupine integration for "Hey Jarvis" detection

**Key Responsibilities**:
- Initialize Porcupine SDK with "Hey Jarvis" keyword
- Continuous audio monitoring at 16kHz sample rate
- CPU-efficient processing (< 5% average usage)
- Handle audio permission changes
- Trigger callbacks on wake word detection

**Performance Requirements**:
- False positive rate: < 1 per hour
- Detection latency: < 2 seconds
- CPU usage: < 5% average
- Memory usage: < 20MB

**Key Methods**:
```kotlin
class WakeWordService {
    // Porcupine integration
    private fun initializePorcupine()
    private fun startListening()
    private fun stopListening()
    
    // Audio processing
    private fun processAudioFrame(frame: ShortArray)
    private fun onWakeWordDetected()
    
    // Resource management
    private fun releaseResources()
}
```

#### 1.4 ASTAWebSocketClient (Kotlin)

**Purpose**: Real-time bidirectional communication with ASTA backend

**Key Responsibilities**:
- Establish WebSocket connection with JWT authentication
- Handle connection lifecycle (connect, disconnect, reconnect)
- Send/receive messages with proper error handling
- Implement exponential backoff for reconnection
- Manage ping/pong heartbeat mechanism

**Connection Management**:
- URL: `wss://[backend-url]/voice/ws?token=[JWT_Token]`
- Reconnection: Exponential backoff, max 5 attempts
- Heartbeat: Ping every 30s, timeout after 10s
- Network change handling: Automatic reconnection

**Message Types**:
- Outbound: audio chunks, text messages, control signals
- Inbound: transcript, response, audio, stage updates, errors

**Key Methods**:
```kotlin
class ASTAWebSocketClient {
    // Connection management
    fun connect(url: String, token: String)
    fun disconnect()
    private fun reconnectWithBackoff()
    
    // Message handling
    fun sendAudioChunk(audioData: ByteArray)
    fun sendTextMessage(message: String)
    private fun handleIncomingMessage(message: String)
    
    // Heartbeat management
    private fun startHeartbeat()
    private fun sendPing()
    private fun handlePong()
}
```

#### 1.5 AudioStreamer (Kotlin)

**Purpose**: Audio recording, streaming, and playback management

**Key Responsibilities**:
- Record audio at 16kHz PCM 16-bit mono
- Stream audio chunks to backend via WebSocket
- Play received PCM audio at 24kHz 16-bit
- Manage audio resources efficiently
- Handle audio session interruptions

**Audio Specifications**:
- Recording: 16kHz, PCM 16-bit, Mono, < 500ms latency
- Playback: 24kHz, PCM 16-bit, Stereo support
- Buffer management: Circular buffers for smooth streaming
- Resource cleanup: Immediate release when not in use

**Key Methods**:
```kotlin
class AudioStreamer {
    // Recording
    fun startRecording()
    fun stopRecording()
    private fun streamAudioChunk(chunk: ByteArray)
    
    // Playback
    fun playAudio(audioData: ByteArray)
    private fun queueAudioForPlayback(chunk: ByteArray)
    
    // Resource management
    private fun releaseRecordingResources()
    private fun releasePlaybackResources()
}
```

### 2. Flutter UI Architecture

#### 2.1 Jarvis Orb Widget

**Purpose**: Primary visual interface showing ASTA's state and enabling user interaction

**Visual States**:
1. **Idle State**: Gentle pulsing blue orb, "TAP TO TALK" text
2. **Listening State**: Active pulsing animation, "LISTENING" text
3. **Speaking State**: Wave rings emanating from orb, "SPEAKING" text

**Color Palette**:
- Primary: #1E88E5 (Blue 600)
- Accent: #4FC3F7 (Light Blue 300)
- Background: #050A18 (Dark Blue)

**Animation Requirements**:
- 60 FPS smooth transitions
- State change animations: 300ms duration
- Continuous animations: Sinusoidal easing
- Touch feedback: Haptic response + visual ripple

**Key Components**:
```dart
class JarvisOrb extends StatefulWidget {
  // State management
  OrbState currentState;
  
  // Animation controllers
  AnimationController pulseController;
  AnimationController waveController;
  AnimationController transitionController;
  
  // User interaction
  void onTap();
  void updateState(OrbState newState);
}
```

#### 2.2 Stage Feed Widget

**Purpose**: Display real-time workflow stage updates from backend

**Key Responsibilities**:
- Show current workflow stage name
- Display stage progress indicators
- Handle stage transition animations
- Support different workflow types

**Design Elements**:
- Stage name display with workflow icon
- Progress indicator (if applicable)
- Smooth text transitions
- Workflow-specific color coding

#### 2.3 Method Channel Integration

**Purpose**: Flutter-to-Kotlin communication for triggering native actions

**Channel Name**: `com.asta/voice`

**Supported Methods**:
- `startListening`: Initiate audio recording and WebSocket connection
- `stopListening`: Stop audio recording
- `sendText`: Send text message to backend via WebSocket

**Error Handling**: All methods return success/error results to Flutter

#### 2.4 Event Channel Integration

**Purpose**: Kotlin-to-Flutter event streaming for real-time updates

**Channel Name**: `com.asta/events`

**Event Types**:
- `connected`: WebSocket connection established
- `transcript`: User speech transcription received
- `response`: ASTA text response received
- `audio`: Audio data for playback
- `stage`: Workflow stage update
- `error`: Error message for user display

### 3. Backend Integration Design

#### 3.1 WebSocket Communication Protocol

**Connection Establishment**:
```
Client → Server: WebSocket handshake with JWT token
Server → Client: {"type": "connected", "message": "ASTA Online"}
```

**Audio Streaming Protocol**:
```
Client → Server: {"type": "audio", "data": base64_audio_chunk}
Server → Client: {"type": "transcript", "text": "transcribed speech"}
Server → Client: {"type": "response", "text": "ASTA response"}
Server → Client: {"type": "audio", "data": base64_tts_audio}
```

**Stage Updates Protocol**:
```
Server → Client: {"type": "stage", "workflow": "research", "stage": "web_search", "detail": "Searching for quantum computing papers"}
```

**Error Handling Protocol**:
```
Server → Client: {"type": "error", "code": "STT_FAILED", "message": "Speech recognition failed"}
```

#### 3.2 Session Management

**Session Lifecycle**:
1. Client generates UUID for session_id
2. Session context maintained in backend memory layer
3. Session persisted to MongoDB on completion
4. Session expires after 30 minutes of inactivity

**Session Data Structure**:
```json
{
  "session_id": "uuid",
  "user_id": "karthik",
  "workflow_type": "research",
  "start_time": "2026-04-20T10:00:00Z",
  "messages": [...],
  "context": {...},
  "status": "active"
}
```

#### 3.3 Authentication Integration

**JWT Token Management**:
- Token stored in Android EncryptedSharedPreferences
- Token included in WebSocket connection query parameter
- Token validated on every WebSocket message
- 401 errors trigger user notification and reconnection

**Security Measures**:
- HTTPS/WSS only for production
- Token rotation support (future enhancement)
- Audio data not logged in production builds
- Immediate buffer clearing after transmission

### 4. Data Models and Contracts

#### 4.1 WebSocket Message Models

```kotlin
// Outbound messages
data class AudioMessage(
    val type: String = "audio",
    val data: String, // base64 encoded
    val session_id: String
)

data class TextMessage(
    val type: String = "text",
    val message: String,
    val session_id: String,
    val workflow_hint: String? = null
)

// Inbound messages
data class TranscriptMessage(
    val type: String,
    val text: String,
    val confidence: Float
)

data class ResponseMessage(
    val type: String,
    val text: String,
    val workflow_type: String
)

data class StageMessage(
    val type: String,
    val workflow: String,
    val stage: String,
    val detail: String
)
```

#### 4.2 Flutter Event Models

```dart
class ASTAEvent {
  final String type;
  final Map<String, dynamic> data;
  final DateTime timestamp;
}

class OrbState {
  final StateType type; // idle, listening, speaking
  final String displayText;
  final Color primaryColor;
  final bool isInteractive;
}

class StageUpdate {
  final String workflow;
  final String stageName;
  final String detail;
  final double? progress;
}
```

### 5. Error Handling and Recovery Design

#### 5.1 Connection Error Handling

**WebSocket Connection Failures**:
1. Display "Connection lost, retrying..." message
2. Implement exponential backoff (1s, 2s, 4s, 8s, 16s)
3. Maximum 5 retry attempts
4. Fallback to offline mode after max retries

**Network Change Handling**:
1. Monitor network connectivity changes
2. Automatically reconnect when network restored
3. Resume audio streaming if session was active
4. Notify user of connection status changes

#### 5.2 Audio Error Handling

**Recording Failures**:
1. Display "Microphone error" message
2. Return to idle state
3. Log detailed error for debugging
4. Attempt to reinitialize audio recorder

**Playback Failures**:
1. Display "Audio playback error" message
2. Continue with text-only response
3. Log error details
4. Release and reinitialize audio player

#### 5.3 Service Recovery

**Foreground Service Crashes**:
1. Android system auto-restart with START_STICKY
2. Service recreates wake word detection
3. Notification restored within 5 seconds
4. MainActivity rebinds to service automatically

**Wake Word Service Failures**:
1. Foreground service detects failure
2. Restart wake word service
3. Reinitialize Porcupine SDK
4. Log failure for analysis

### 6. Performance Optimization Design

#### 6.1 Battery Optimization

**Wake Word Service**:
- Use Porcupine's optimized algorithms
- Target < 5% CPU usage during idle monitoring
- Implement audio processing on background thread
- Use efficient audio buffer management

**WebSocket Management**:
- Close idle connections after 5 minutes
- Implement connection pooling for multiple sessions
- Use compression for large messages
- Batch small messages when possible

#### 6.2 Memory Management

**Audio Buffers**:
- Use circular buffers for streaming
- Immediate cleanup after transmission
- Limit buffer size to prevent memory leaks
- Monitor memory usage in production

**Service Memory**:
- Target < 50MB RAM for foreground service
- Implement proper lifecycle management
- Release resources in onDestroy()
- Use weak references for callbacks

#### 6.3 UI Performance

**Flutter Animations**:
- Maintain 60 FPS for all animations
- Use efficient animation controllers
- Implement proper dispose() methods
- Optimize custom paint operations

**State Management**:
- Use efficient state management patterns
- Minimize widget rebuilds
- Implement proper key usage
- Cache expensive computations

### 7. Security Design

#### 7.1 Data Protection

**Token Storage**:
- Use Android EncryptedSharedPreferences
- AES-256 encryption for sensitive data
- Secure key derivation from Android Keystore
- Automatic token cleanup on app uninstall

**Audio Data Security**:
- No persistent storage of audio data
- Immediate buffer clearing after transmission
- Encrypted transmission over WSS
- No audio logging in production builds

#### 7.2 Permission Management

**Runtime Permissions**:
- Request RECORD_AUDIO permission on first use
- Provide clear rationale for permission request
- Graceful degradation when permission denied
- Re-request permission when needed

**Manifest Permissions**:
```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
```

### 8. Build Configuration Design

#### 8.1 Gradle Dependencies

**Core Dependencies**:
```kotlin
dependencies {
    // OkHttp for WebSocket support
    implementation 'com.squareup.okhttp3:okhttp:4.12.0'
    
    // Picovoice Porcupine for wake word detection
    implementation 'ai.picovoice:porcupine-android:3.0.0'
    
    // Flutter module integration
    implementation project(':flutter')
    
    // Kotlin coroutines
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3'
    
    // Encrypted SharedPreferences
    implementation 'androidx.security:security-crypto:1.1.0-alpha06'
}
```

**Build Configuration**:
```kotlin
android {
    compileSdk 36
    
    defaultConfig {
        minSdk 26
        targetSdk 36
        versionCode 1
        versionName "1.0"
    }
    
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }
    
    kotlinOptions {
        jvmTarget = '1.8'
    }
}
```

#### 8.2 Flutter Module Integration

**Flutter Module Structure**:
```
flutter_module/
├── lib/
│   ├── main.dart
│   ├── screens/
│   │   └── jarvis_screen.dart
│   └── widgets/
│       ├── jarvis_orb.dart
│       └── stage_feed.dart
├── pubspec.yaml
└── android/
    └── app/
        └── src/
            └── main/
                └── kotlin/
```

**Integration Configuration**:
```kotlin
// In MainActivity
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        // Setup method channel
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.asta/voice")
            .setMethodCallHandler { call, result ->
                handleMethodCall(call, result)
            }
        
        // Setup event channel
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, "com.asta/events")
            .setStreamHandler(eventStreamHandler)
    }
}
```

### 9. Testing Strategy Design

#### 9.1 Unit Testing

**Kotlin Components**:
- WebSocket client connection/disconnection logic
- Audio streaming buffer management
- Wake word service state management
- Error handling and recovery mechanisms

**Flutter Components**:
- Orb state transitions and animations
- Method/Event channel communication
- UI state management
- Error display logic

#### 9.2 Integration Testing

**End-to-End Voice Flow**:
1. Wake word detection → UI launch
2. Audio recording → WebSocket streaming
3. Backend response → Audio playback
4. UI state updates → Session completion

**Backend Integration**:
1. WebSocket connection with JWT authentication
2. Message protocol compliance
3. Error response handling
4. Session management

#### 9.3 Performance Testing

**Battery Usage**:
- Monitor CPU usage during wake word detection
- Measure battery drain over 24-hour period
- Test with various Android power management settings

**Memory Usage**:
- Monitor service memory consumption
- Test for memory leaks during extended usage
- Verify proper resource cleanup

**Audio Latency**:
- Measure end-to-end voice response latency
- Test audio quality at different network conditions
- Verify real-time streaming performance

### 10. Deployment and Distribution

#### 10.1 Build Variants

**Debug Build**:
- Logging enabled for all components
- Development backend URL
- Debug symbols included
- Performance monitoring enabled

**Release Build**:
- Production backend URL
- Logging disabled for sensitive data
- Code obfuscation enabled
- Optimized for size and performance

#### 10.2 Configuration Management

**Environment-Specific Settings**:
```kotlin
object Config {
    const val BACKEND_URL = BuildConfig.BACKEND_URL
    const val JWT_TOKEN = BuildConfig.JWT_TOKEN
    const val DEBUG_LOGGING = BuildConfig.DEBUG
    const val WAKE_WORD_SENSITIVITY = 0.5f
}
```

**Build-Time Configuration**:
```kotlin
buildTypes {
    debug {
        buildConfigField "String", "BACKEND_URL", "\"wss://dev.asta.ai\""
        buildConfigField "String", "JWT_TOKEN", "\"dev_token\""
    }
    release {
        buildConfigField "String", "BACKEND_URL", "\"wss://api.asta.ai\""
        buildConfigField "String", "JWT_TOKEN", "\"prod_token\""
    }
}
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
1. MainActivity setup with Flutter integration
2. Method/Event channel implementation
3. Basic WebSocket client with authentication
4. Foreground service with notification

### Phase 2: Audio Pipeline (Week 3-4)
1. Wake word service with Porcupine integration
2. Audio recording and streaming implementation
3. Audio playback system
4. Basic error handling

### Phase 3: UI Implementation (Week 5-6)
1. Jarvis Orb widget with all states
2. Stage feed display
3. Transcript and response UI
4. Animation system

### Phase 4: Integration and Testing (Week 7-8)
1. End-to-end voice flow testing
2. Backend integration verification
3. Performance optimization
4. Error handling refinement

### Phase 5: Polish and Deployment (Week 9-10)
1. UI/UX refinements
2. Battery and performance optimization
3. Security hardening
4. Production deployment preparation

## Success Criteria

### Functional Requirements
- [ ] Wake word detection with < 2 second latency
- [ ] End-to-end voice conversation completion
- [ ] All 6 workflow types accessible via voice
- [ ] Real-time WebSocket communication
- [ ] Proper error handling and recovery

### Performance Requirements
- [ ] < 5% CPU usage during idle monitoring
- [ ] < 50MB RAM usage for foreground service
- [ ] < 1 second end-to-end voice latency
- [ ] 60 FPS UI animations
- [ ] 24-hour battery life with normal usage

### Security Requirements
- [ ] JWT authentication for all backend communication
- [ ] Encrypted storage of sensitive data
- [ ] No audio data persistence
- [ ] Proper permission handling

This design document provides the comprehensive technical foundation for implementing all 23 requirements while ensuring scalability, maintainability, and optimal user experience.