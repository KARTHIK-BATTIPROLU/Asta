@echo off
REM ASTA Startup Script for Windows
REM Automatically configures and starts ASTA with ngrok

echo ============================================================
echo ASTA Mobile App - Startup Script
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/3] Checking ngrok...
curl -s http://127.0.0.1:4040/api/tunnels >nul 2>&1
if errorlevel 1 (
    echo ngrok is not running
    echo.
    echo Please start ngrok in a separate terminal:
    echo   ngrok http 8000
    echo.
    echo Then run this script again.
    pause
    exit /b 1
) else (
    echo ✓ ngrok is running
)

echo.
echo [2/3] Fetching ngrok URL and updating Android config...
python get_ngrok_url.py
if errorlevel 1 (
    echo.
    echo ERROR: Failed to update configuration
    pause
    exit /b 1
)

echo.
echo [3/3] Starting ASTA backend...
echo.
echo Backend will start in a new window.
echo Keep both this window and the backend window open.
echo.
start "ASTA Backend" cmd /k python run.py

echo.
echo ============================================================
echo ASTA is ready!
echo ============================================================
echo.
echo Next steps:
echo 1. Open Android Studio
echo 2. Open the "ASTA MOBILE" folder
echo 3. Build and run the app
echo.
echo The app will automatically connect to the backend.
echo.
echo Press any key to exit this window...
pause >nul
