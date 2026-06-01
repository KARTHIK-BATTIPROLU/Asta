#!/bin/bash
# ASTA Startup Script for Linux/Mac
# Automatically configures and starts ASTA with ngrok

echo "============================================================"
echo "ASTA Mobile App - Startup Script"
echo "============================================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8+ from https://www.python.org/"
    exit 1
fi

echo "[1/3] Checking ngrok..."
if curl -s http://127.0.0.1:4040/api/tunnels > /dev/null 2>&1; then
    echo "✓ ngrok is running"
else
    echo "ngrok is not running"
    echo ""
    echo "Please start ngrok in a separate terminal:"
    echo "  ngrok http 8000"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo ""
echo "[2/3] Fetching ngrok URL and updating Android config..."
python3 get_ngrok_url.py
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to update configuration"
    exit 1
fi

echo ""
echo "[3/3] Starting ASTA backend..."
echo ""
echo "Backend will start in the background."
echo "Check backend.log for output."
echo ""

# Start backend in background
nohup python3 run.py > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

echo ""
echo "============================================================"
echo "ASTA is ready!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Open Android Studio"
echo "2. Open the 'ASTA MOBILE' folder"
echo "3. Build and run the app"
echo ""
echo "The app will automatically connect to the backend."
echo ""
echo "To stop the backend:"
echo "  kill $BACKEND_PID"
echo ""
echo "Backend logs: tail -f backend.log"
echo ""
