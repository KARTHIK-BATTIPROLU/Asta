#!/bin/bash
# Complete setup script for Android OpenWakeWord integration

set -e  # Exit on error

echo "=========================================="
echo "ASTA Android OpenWakeWord Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python not found. Please install Python 3.7+${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python found${NC}"

# Check if openwakeword is installed
if ! python -c "import openwakeword" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  openwakeword not installed${NC}"
    echo "Installing openwakeword..."
    pip install openwakeword
fi

echo -e "${GREEN}✅ openwakeword installed${NC}"
echo ""

# Step 1: Extract models
echo "Step 1: Extracting ONNX models..."
python extract_wake_word_models.py

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Model extraction failed${NC}"
    exit 1
fi

echo ""

# Step 2: Copy full implementation
echo "Step 2: Installing full OpenWakeWord implementation..."

SRC="ASTA MOBILE/app/src/main/java/com/example/asta/service/OpenWakeWordEngine_FULL_IMPLEMENTATION.kt"
DST="ASTA MOBILE/app/src/main/java/com/example/asta/service/OpenWakeWordEngine.kt"

if [ ! -f "$SRC" ]; then
    echo -e "${RED}❌ Full implementation file not found: $SRC${NC}"
    exit 1
fi

cp "$SRC" "$DST"
echo -e "${GREEN}✅ Copied full implementation to OpenWakeWordEngine.kt${NC}"
echo ""

# Step 3: Verify assets
echo "Step 3: Verifying model files..."

ASSETS_DIR="ASTA MOBILE/app/src/main/assets"
MELSPEC="$ASSETS_DIR/melspectrogram.onnx"
WAKEWORD="$ASSETS_DIR/hey_jarvis.onnx"

if [ ! -f "$MELSPEC" ]; then
    echo -e "${RED}❌ Missing: melspectrogram.onnx${NC}"
    exit 1
fi

if [ ! -f "$WAKEWORD" ]; then
    echo -e "${RED}❌ Missing: hey_jarvis.onnx${NC}"
    exit 1
fi

MELSPEC_SIZE=$(du -h "$MELSPEC" | cut -f1)
WAKEWORD_SIZE=$(du -h "$WAKEWORD" | cut -f1)

echo -e "${GREEN}✅ melspectrogram.onnx ($MELSPEC_SIZE)${NC}"
echo -e "${GREEN}✅ hey_jarvis.onnx ($WAKEWORD_SIZE)${NC}"
echo ""

# Step 4: Summary
echo "=========================================="
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Open Android Studio"
echo "2. Build the project: ./gradlew assembleDebug"
echo "3. Install on device and test"
echo ""
echo "Files modified:"
echo "  - OpenWakeWordEngine.kt (full implementation)"
echo "  - assets/melspectrogram.onnx (added)"
echo "  - assets/hey_jarvis.onnx (added)"
echo ""
echo "To test:"
echo "  - Say 'Hey Jarvis' near the device"
echo "  - Watch logcat for detection messages"
echo ""
echo "For troubleshooting, see:"
echo "  - ANDROID_OPENWAKEWORD_SETUP.md"
echo "  - ANDROID_WAKE_WORD_SUMMARY.md"
echo ""
