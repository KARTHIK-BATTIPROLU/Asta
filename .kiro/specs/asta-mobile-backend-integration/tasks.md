# Implementation Tasks

## Task Overview

This document outlines the implementation tasks for integrating the ASTA MOBILE Android application with the production ASTA backend. Tasks are organized by implementation phases and include verification criteria for each deliverable.

## Phase 1: Project Setup and Core Infrastructure

### Task 1.1: Android Project Configuration
- [ ] Update build.gradle with required dependencies (OkHttp 4.12.0+, Porcupine 3.0.0+, Kotlin coroutines)
- [ ] Set minSdk to 26 and targetSdk to 36
- [ ] Add required permissions to AndroidManifest.xml (RECORD_AUDIO, INTERNET, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE, WAKE_LOCK)
- [ ] Configure build variants for debug/release with different backend URLs
- [ ] Set up Flutter module integration in build configuration

**Verification**: Project builds successfully without errors, all dependencies resolve correctly

### Task 1.2: Configuration Management System
- [ ] Create ConfigManager class for backend URL and JWT token management
- [ ] Implement EncryptedSharedPreferences for secure token storage
- [ ] Add configuration validation (URL format, token presence)
- [ ] Create debug/release configuration variants
- [ ] Implement configuration persistence across app restarts

**Verification**: Configuration loads correctly, tokens stored securely, URL validation works

### Task 1.3: MainActivity Foundation
- [ ] Create MainActivity extending FlutterActivity
- [ ] Implement Flutter engine initialization
- [ ] Set up basic permission request flow for RECORD_AUDIO
- [ ] Create service binding infrastructure for ASTAForegroundService
- [ ] Implement basic lifecycle management (onCreate, onDestroy, onResume, onPause)

**Verification**: MainActivity launches Flutter UI, permission requests work, service binding established

## Phase 2: Foreground Service and Wake Word Detection

### Task 2.1: ASTAForegroundService Implementation
- [ ] Create ASTAForegroundService extending Service
- [ ] Implement notification channel creation and management
- [ ] Create persistent notification with "ASTA Online - Say 'Hey Jarvis' to wake me up" text
- [ ] Implement LocalBinder for MainActivity communication
- [ ] Configure service as START_STICKY for automatic restart
- [ ] Declare foregroundServiceType as "microphone" in AndroidManifest

**Verification**: Service starts on app launch, notification appears, service survives app force-stop and restarts

### Task 2.2: WakeWordService Integration
- [ ] Integrate Picovoice Porcupine SDK for "Hey Jarvis" detection
- [ ] Implement continuous audio monitoring at 16kHz sample rate
- [ ] Create wake word detection callback system
- [ ] Implement CPU-efficient processing (target < 5% usage)
- [ ] Add permission handling for audio recording
- [ ] Implement proper resource cleanup and error handling

**Verification**: Wake word detected within 2 seconds, CPU usage < 5%, false positives < 1/hour

### Task 2.3: Wake Word Callback System
- [ ] Create callback interface between WakeWordService and ASTAForegroundService
- [ ] Implement callback propagation from ASTAForegroundService to MainActivity
- [ ] Add wake word detection event handling in MainActivity
- [ ] Implement screen wake functionality for wake word activation
- [ ] Create Jarvis screen launch logic on wake word detection

**Verification**: "Hey Jarvis" triggers screen wake and Jarvis UI launch, callbacks work reliably

## Phase 3: WebSocket Communication

### Task 3.1: ASTAWebSocketClient Implementation
- [ ] Create WebSocket client using OkHttp library
- [ ] Implement connection establishment with JWT authentication (wss://[backend-url]/voice/ws?token=[JWT_Token])
- [ ] Add connection state management (connecting, connected, disconnected, error)
- [ ] Implement exponential backoff reconnection (max 5 attempts)
- [ ] Create ping/pong heartbeat mechanism (30s interval, 10s timeout)
- [ ] Add network change detection and automatic reconnection

**Verification**: WebSocket connects successfully, receives "connected" message, reconnection works

### Task 3.2: WebSocket Message Protocol
- [ ] Define message data classes for all message types (audio, text, transcript, response, stage, error)
- [ ] Implement JSON serialization/deserialization for messages
- [ ] Create message routing system for different message types
- [ ] Add message validation and error handling
- [ ] Implement session_id inclusion in all outbound messages

**Verification**: All message types serialize/deserialize correctly, routing works for each type

### Task 3.3: WebSocket Error Handling
- [ ] Implement connection failure handling with user notifications
- [ ] Add retry logic with exponential backoff
- [ ] Create error message display system
- [ ] Implement graceful degradation for network issues
- [ ] Add connection status indicators for UI

**Verification**: Connection errors display appropriate messages, retry logic works, status updates correctly

## Phase 4: Audio Pipeline

### Task 4.1: AudioStreamer - Recording Implementation
- [ ] Create AudioStreamer class for audio recording management
- [ ] Implement 16kHz PCM 16-bit mono recording
- [ ] Create real-time audio streaming to WebSocket (< 500ms latency)
- [ ] Implement circular buffer management for smooth streaming
- [ ] Add audio session management and interruption handling
- [ ] Create proper resource cleanup and error handling

**Verification**: Audio records at correct format, streams in real-time, latency < 500ms

### Task 4.2: AudioStreamer - Playback Implementation
- [ ] Implement PCM audio playback at 24kHz 16-bit
- [ ] Create audio queue management for received chunks
- [ ] Implement seamless playback without gaps or overlaps
- [ ] Add playback completion callbacks
- [ ] Create audio focus management for Android system
- [ ] Implement proper resource cleanup

**Verification**: Audio plays smoothly, no gaps/overlaps, completion callbacks work

### Task 4.3: Audio Resource Management
- [ ] Implement immediate resource release when not in use
- [ ] Create audio session state management
- [ ] Add memory management for audio buffers
- [ ] Implement audio permission change handling
- [ ] Create audio error recovery mechanisms

**Verification**: Resources released properly, no memory leaks, permission changes handled

## Phase 5: Flutter UI Implementation

### Task 5.1: Method Channel Setup
- [ ] Create Method Channel with name "com.asta/voice"
- [ ] Implement "startListening" method to start AudioStreamer and WebSocket
- [ ] Implement "stopListening" method to stop AudioStreamer
- [ ] Implement "sendText" method to send text messages via WebSocket
- [ ] Add proper error handling and result reporting to Flutter

**Verification**: All method calls work from Flutter, success/error results returned correctly

### Task 5.2: Event Channel Setup
- [ ] Create Event Channel with name "com.asta/events"
- [ ] Implement event streaming for all message types (connected, transcript, response, audio, stage, error)
- [ ] Add WebSocket connection state change events
- [ ] Implement proper listener lifecycle management (onListen, onCancel)
- [ ] Create event data serialization for Flutter consumption

**Verification**: Events stream correctly to Flutter, listener lifecycle managed properly

### Task 5.3: Jarvis Orb Widget
- [ ] Create JarvisOrb StatefulWidget with three states (Idle, Listening, Speaking)
- [ ] Implement smooth 60 FPS animations for all states
- [ ] Create pulsing animation for Idle state with "TAP TO TALK" text
- [ ] Implement active pulsing for Listening state with "LISTENING" text
- [ ] Create wave ring animations for Speaking state with "SPEAKING" text
- [ ] Use specified color palette (#1E88E5, #4FC3F7, #050A18)

**Verification**: All three states display correctly, animations run at 60 FPS, colors match specification

### Task 5.4: Jarvis Orb Interaction
- [ ] Implement tap detection with minimum 110 pixel radius touch target
- [ ] Add haptic feedback on tap events
- [ ] Create tap-to-start-listening functionality in Idle state
- [ ] Implement tap-to-stop-listening functionality in Listening state
- [ ] Disable tap events during Speaking state
- [ ] Add smooth state transition animations (300ms duration)

**Verification**: Tap detection works reliably, haptic feedback triggers, state transitions smooth

### Task 5.5: Transcript and Response Display
- [ ] Create text display area below Jarvis Orb
- [ ] Implement transcript display with minimum 14sp font size
- [ ] Create response text display below transcript
- [ ] Add Stage Feed display showing current workflow stage
- [ ] Implement text replacement for new transcript/response messages
- [ ] Create readable text styling and layout

**Verification**: Text displays correctly, font size readable, updates work for new messages

## Phase 6: Voice Session Management

### Task 6.1: Voice Session Lifecycle
- [ ] Implement complete voice session state machine (Idle → Speaking → Listening → Processing → Speaking → Idle)
- [ ] Create automatic recording stop after 2 seconds of silence
- [ ] Implement session timeout after 7 seconds of no speech
- [ ] Add back button handling to cancel sessions
- [ ] Create automatic return to idle after response completion

**Verification**: State machine works correctly, timeouts function, back button cancels sessions

### Task 6.2: Wake Word Session Flow
- [ ] Implement wake prompt playback ("Yes, how can I help?") on wake word detection
- [ ] Create automatic listening start after wake prompt completion
- [ ] Add screen-over-lock functionality for wake word activation
- [ ] Implement automatic Jarvis screen closure after session completion
- [ ] Create proper session cleanup on completion

**Verification**: Wake word triggers complete flow, screen wakes over lock, sessions complete properly

### Task 6.3: Session Context Management
- [ ] Implement unique session ID generation for each conversation
- [ ] Create session persistence until user starts new conversation
- [ ] Add session ID inclusion in all backend requests
- [ ] Implement new session creation on backend session expiry
- [ ] Create session state synchronization between components

**Verification**: Session IDs generated correctly, context maintained, new sessions created when needed

## Phase 7: Error Handling and Recovery

### Task 7.1: Connection Error Handling
- [ ] Implement "Connection lost, retrying..." user notifications
- [ ] Create backend error response display system
- [ ] Add connection status indicators in UI
- [ ] Implement graceful fallback for network issues
- [ ] Create error logging system for debugging

**Verification**: Error messages display correctly, connection status updates, logging works

### Task 7.2: Audio Error Handling
- [ ] Implement "Microphone error" display for recording failures
- [ ] Create "Audio playback error" display for playback failures
- [ ] Add automatic return to idle state on audio errors
- [ ] Implement audio resource reinitialization on errors
- [ ] Create detailed error logging for audio issues

**Verification**: Audio errors display appropriate messages, state returns to idle, resources reinitialize

### Task 7.3: Service Recovery
- [ ] Implement automatic foreground service restart detection
- [ ] Create service rebinding logic in MainActivity
- [ ] Add wake word service restart on foreground service recovery
- [ ] Implement notification restoration after service restart
- [ ] Create service health monitoring and recovery

**Verification**: Services restart automatically, MainActivity rebinds, wake word detection resumes

## Phase 8: Performance Optimization

### Task 8.1: Battery Optimization
- [ ] Optimize wake word service for < 5% CPU usage
- [ ] Implement efficient audio buffer management
- [ ] Create WebSocket connection pooling and idle timeout (5 minutes)
- [ ] Add Doze mode exemption only for foreground service
- [ ] Implement background processing optimization

**Verification**: CPU usage < 5% during idle, battery drain acceptable, Doze mode handled

### Task 8.2: Memory Optimization
- [ ] Implement immediate audio buffer cleanup after transmission
- [ ] Create memory monitoring for foreground service (< 50MB target)
- [ ] Add proper lifecycle management for all components
- [ ] Implement weak references for callback systems
- [ ] Create memory leak detection and prevention

**Verification**: Memory usage < 50MB for service, no memory leaks detected, cleanup works

### Task 8.3: UI Performance Optimization
- [ ] Ensure 60 FPS for all Jarvis Orb animations
- [ ] Optimize Flutter widget rebuilds
- [ ] Implement efficient state management patterns
- [ ] Create smooth transition animations without jank
- [ ] Add performance monitoring for UI components

**Verification**: Animations maintain 60 FPS, no frame drops, transitions smooth

## Phase 9: Security Implementation

### Task 9.1: Authentication Security
- [ ] Implement JWT token secure storage using EncryptedSharedPreferences
- [ ] Add AES-256 encryption for sensitive data
- [ ] Create secure key derivation from Android Keystore
- [ ] Implement token validation before each request
- [ ] Add 401 error handling with user notification

**Verification**: Tokens stored securely, encryption works, 401 errors handled properly

### Task 9.2: Data Security
- [ ] Implement immediate audio buffer clearing after transmission
- [ ] Ensure no persistent storage of audio data
- [ ] Create production build configuration with no sensitive logging
- [ ] Add HTTPS/WSS enforcement for production
- [ ] Implement secure data transmission protocols

**Verification**: No audio data persisted, production logging secure, HTTPS enforced

### Task 9.3: Permission Security
- [ ] Implement runtime permission request with clear rationale
- [ ] Create graceful degradation when permissions denied
- [ ] Add permission re-request functionality when needed
- [ ] Implement permission change handling during app usage
- [ ] Create secure permission state management

**Verification**: Permission requests work, rationale clear, degradation graceful

## Phase 10: Testing and Validation

### Task 10.1: Unit Testing
- [ ] Create unit tests for WebSocket client connection logic
- [ ] Implement tests for audio streaming buffer management
- [ ] Add tests for wake word service state management
- [ ] Create tests for error handling and recovery mechanisms
- [ ] Implement tests for Flutter UI state management

**Verification**: All unit tests pass, code coverage > 80%, edge cases covered

### Task 10.2: Integration Testing
- [ ] Create end-to-end voice flow tests (wake word → response → idle)
- [ ] Implement backend integration tests with all 6 workflow types
- [ ] Add WebSocket protocol compliance tests
- [ ] Create session management integration tests
- [ ] Implement error scenario integration tests

**Verification**: End-to-end flows work, all workflows accessible, error scenarios handled

### Task 10.3: Performance Testing
- [ ] Measure and verify wake word detection latency < 2 seconds
- [ ] Test end-to-end voice response latency < 1 second
- [ ] Verify CPU usage < 5% during idle monitoring
- [ ] Test memory usage < 50MB for foreground service
- [ ] Validate 60 FPS UI animations under load

**Verification**: All performance targets met, latency within limits, resource usage optimal

### Task 10.4: Device Compatibility Testing
- [ ] Test on Android API 26-36 devices
- [ ] Verify functionality on different screen sizes and densities
- [ ] Test with various Android OEM customizations
- [ ] Validate performance on low-end and high-end devices
- [ ] Test with different audio hardware configurations

**Verification**: App works on target devices, performance acceptable across range

## Phase 11: Production Readiness

### Task 11.1: Build Configuration
- [ ] Configure release build with production backend URL
- [ ] Implement code obfuscation and optimization
- [ ] Create signing configuration for release builds
- [ ] Add crash reporting and analytics integration
- [ ] Configure build variants for different environments

**Verification**: Release builds correctly, obfuscation works, signing configured

### Task 11.2: Deployment Preparation
- [ ] Create app store listing materials and screenshots
- [ ] Implement version management and update mechanisms
- [ ] Add user onboarding and tutorial flows
- [ ] Create privacy policy and terms of service integration
- [ ] Implement feedback and support mechanisms

**Verification**: Store materials ready, onboarding flows work, legal compliance met

### Task 11.3: Monitoring and Analytics
- [ ] Implement crash reporting (Firebase Crashlytics or similar)
- [ ] Add performance monitoring for key metrics
- [ ] Create user analytics for feature usage
- [ ] Implement error tracking and alerting
- [ ] Add health monitoring dashboards

**Verification**: Monitoring systems active, alerts configured, dashboards functional

## Correctness Properties for Property-Based Testing

### Property 1: Wake Word Detection Reliability
**Property**: For any valid "Hey Jarvis" utterance, the system SHALL detect the wake word within 2 seconds with probability > 99%

**Test Strategy**: Generate variations of "Hey Jarvis" with different accents, volumes, and background noise levels

### Property 2: Audio Streaming Integrity
**Property**: For any audio chunk sent to the backend, the chunk SHALL arrive without corruption and in correct sequence

**Test Strategy**: Send known audio patterns and verify bit-perfect transmission and ordering

### Property 3: WebSocket Connection Resilience
**Property**: For any network interruption lasting < 30 seconds, the WebSocket connection SHALL automatically recover without data loss

**Test Strategy**: Simulate various network failure scenarios and verify recovery behavior

### Property 4: Session Context Preservation
**Property**: For any conversation within a single session, the backend SHALL maintain complete context across all message exchanges

**Test Strategy**: Generate multi-turn conversations and verify context retention at each step

### Property 5: UI State Consistency
**Property**: For any voice session state transition, the Jarvis Orb SHALL display the correct visual state within 100ms

**Test Strategy**: Trigger all possible state transitions and measure visual update timing

### Property 6: Resource Cleanup Completeness
**Property**: For any audio session completion, ALL audio resources SHALL be released within 1 second

**Test Strategy**: Monitor resource usage before, during, and after audio sessions

### Property 7: Error Recovery Completeness
**Property**: For any recoverable error condition, the system SHALL return to a functional state within 5 seconds

**Test Strategy**: Inject various error conditions and verify recovery timing and completeness

## Success Criteria

### Functional Success Criteria
- [ ] Wake word detection works reliably with < 2 second latency
- [ ] Complete voice conversations work end-to-end without crashes
- [ ] All 6 backend workflow types accessible via voice interface
- [ ] WebSocket communication maintains real-time performance
- [ ] Error handling provides clear user feedback and recovery

### Performance Success Criteria
- [ ] CPU usage < 5% during idle wake word monitoring
- [ ] Memory usage < 50MB for foreground service
- [ ] End-to-end voice latency < 1 second
- [ ] UI animations maintain 60 FPS consistently
- [ ] Battery life supports 24-hour usage with normal patterns

### Security Success Criteria
- [ ] JWT authentication works for all backend communication
- [ ] Sensitive data encrypted in storage using AES-256
- [ ] No audio data persisted on device
- [ ] Runtime permissions handled gracefully
- [ ] Production builds contain no sensitive logging

### Quality Success Criteria
- [ ] Unit test coverage > 80% for all critical components
- [ ] Integration tests pass for all major user flows
- [ ] Performance tests meet all specified targets
- [ ] App works reliably on Android API 26-36 devices
- [ ] User experience flows smoothly without friction

This comprehensive task list provides the roadmap for implementing all 23 requirements while ensuring quality, performance, and security standards are met throughout the development process.