# ASTA Mobile App Setup Guide

## Overview
This guide will help you set up the ASTA mobile app with automatic ngrok URL detection and a beautiful modern UI.

## Prerequisites
- Python 3.8+
- ngrok installed ([download here](https://ngrok.com/download))
- Android Studio
- Android device or emulator

## Quick Start

### Option 1: Automatic Setup (Recommended)

1. **Run the startup script:**
   ```bash
   python start_asta.py
   ```
   
   This script will:
   - Check if ngrok is running (and optionally start it)
   - Fetch the current ngrok URL
   - Update the Android app configuration automatically
   - Optionally start the backend server

2. **Build and run the Android app:**
   - Open `ASTA MOBILE` folder in Android Studio
   - Build and run the app
   - The app will automatically connect to the correct backend URL

### Option 2: Manual Setup

1. **Start ngrok:**
   ```bash
   ngrok http 8000
   ```

2. **Update Android app with ngrok URL:**
   ```bash
   python get_ngrok_url.py
   ```

3. **Start the backend:**
   ```bash
   python run.py
   ```

4. **Build and run the Android app**

## Features

### 🎨 Beautiful Modern UI
- Material Design 3 components
- Smooth animations and transitions
- Clean, intuitive chat interface
- Status indicators for connection state
- Floating action buttons for voice and send
- Gradient backgrounds and modern color scheme

### 🔄 Dynamic URL Configuration
- Automatic ngrok URL detection
- No need to manually update URLs
- Fallback to manual entry if auto-detection fails
- Connection health checking

### 💬 Enhanced Chat Experience
- Message bubbles with timestamps
- User messages (right, purple)
- Assistant messages (left, light gray)
- Avatar icons for assistant
- Smooth scrolling
- Empty state with welcome message

## UI Components

### Main Screen
- **App Bar**: ASTA logo and settings button
- **Status Card**: Connection status with indicator
- **Chat Area**: Scrollable message list
- **Input Card**: Voice button, text input, send button

### Color Scheme
- **Primary**: Indigo (#6366F1)
- **Accent**: Purple (#8B5CF6)
- **Background**: Light slate (#F8FAFC)
- **User Messages**: Purple gradient
- **Assistant Messages**: Light gray

## Troubleshooting

### App can't connect to backend
1. Check that ngrok is running: `http://127.0.0.1:4040`
2. Verify backend is running: `python run.py`
3. Run the update script: `python get_ngrok_url.py`
4. Rebuild the Android app

### ngrok URL changed
1. Simply run: `python get_ngrok_url.py`
2. Rebuild the Android app
3. Or use the "Manual" button in the app to enter the new URL

### Auto-detection not working
1. Make sure ngrok is running on port 4040
2. Check that the backend is accessible
3. Use manual URL entry in the app

## Backend Endpoints

The backend now includes a new endpoint for dynamic URL fetching:

- `GET /api/ngrok-url` - Returns the current ngrok URL

Example response:
```json
{
  "url": "https://abc123.ngrok-free.app/",
  "status": "active"
}
```

## Development

### Updating the UI
All UI files are in:
- `ASTA MOBILE/app/src/main/res/layout/` - Layout XML files
- `ASTA MOBILE/app/src/main/res/values/colors.xml` - Color definitions
- `ASTA MOBILE/app/src/main/res/drawable/` - Drawable resources

### Updating Network Configuration
- `AstaNetworkClient.kt` - Main network client
- `NgrokUrlFetcher.kt` - URL fetching logic
- `MainActivity.java` - Connection dialog and initialization

## Scripts

### `start_asta.py`
Complete startup automation:
- Checks/starts ngrok
- Fetches URL
- Updates Android config
- Starts backend
- Provides status summary

### `get_ngrok_url.py`
Standalone URL fetcher:
- Queries ngrok API
- Updates Android configuration
- Can be run anytime ngrok URL changes

## Tips

1. **Keep ngrok running**: The URL changes each time ngrok restarts
2. **Use the startup script**: It handles everything automatically
3. **Check the status card**: Shows connection state in the app
4. **Use voice input**: Tap the microphone button for voice commands
5. **Smooth experience**: The new UI is optimized for performance

## Next Steps

- Customize colors in `colors.xml`
- Add more animations
- Implement dark mode
- Add notification support
- Enhance voice features

## Support

If you encounter issues:
1. Check ngrok is running: `http://127.0.0.1:4040`
2. Verify backend health: `http://your-ngrok-url/api/health`
3. Check Android Studio logs
4. Run `python get_ngrok_url.py` to refresh configuration

---

**Enjoy your beautiful ASTA mobile app! 🚀**
