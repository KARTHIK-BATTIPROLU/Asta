@echo off
REM Complete setup script for Android OpenWakeWord integration (Windows)

echo ==========================================
echo ASTA Android OpenWakeWord Setup
echo ==========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.7+
    exit /b 1
)

echo [OK] Python found
echo.

REM Check if openwakeword is installed
python -c "import openwakeword" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] openwakeword not installed
    echo Installing openwakeword...
    pip install openwakeword
)

echo [OK] openwakeword installed
echo.

REM Step 1: Extract models
echo Step 1: Extracting ONNX models...
python extract_wake_word_models.py

if errorlevel 1 (
    echo [ERROR] Model extraction failed
    exit /b 1
)

echo.

REM Step 2: Copy full implementation
echo Step 2: Installing full OpenWakeWord implementation...

set SRC=ASTA MOBILE\app\src\main\java\com\example\asta\service\OpenWakeWordEngine_FULL_IMPLEMENTATION.kt
set DST=ASTA MOBILE\app\src\main\java\com\example\asta\service\OpenWakeWordEngine.kt

if not exist "%SRC%" (
    echo [ERROR] Full implementation file not found: %SRC%
    exit /b 1
)

copy /Y "%SRC%" "%DST%" >nul
echo [OK] Copied full implementation to OpenWakeWordEngine.kt
echo.

REM Step 3: Verify assets
echo Step 3: Verifying model files...

set ASSETS_DIR=ASTA MOBILE\app\src\main\assets
set MELSPEC=%ASSETS_DIR%\melspectrogram.onnx
set WAKEWORD=%ASSETS_DIR%\hey_jarvis.onnx

if not exist "%MELSPEC%" (
    echo [ERROR] Missing: melspectrogram.onnx
    exit /b 1
)

if not exist "%WAKEWORD%" (
    echo [ERROR] Missing: hey_jarvis.onnx
    exit /b 1
)

echo [OK] melspectrogram.onnx
echo [OK] hey_jarvis.onnx
echo.

REM Step 4: Summary
echo ==========================================
echo [SUCCESS] Setup Complete!
echo ==========================================
echo.
echo Next steps:
echo 1. Open Android Studio
echo 2. Build the project: gradlew assembleDebug
echo 3. Install on device and test
echo.
echo Files modified:
echo   - OpenWakeWordEngine.kt (full implementation)
echo   - assets\melspectrogram.onnx (added)
echo   - assets\hey_jarvis.onnx (added)
echo.
echo To test:
echo   - Say 'Hey Jarvis' near the device
echo   - Watch logcat for detection messages
echo.
echo For troubleshooting, see:
echo   - ANDROID_OPENWAKEWORD_SETUP.md
echo   - ANDROID_WAKE_WORD_SUMMARY.md
echo.

pause
