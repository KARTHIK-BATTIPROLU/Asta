#!/bin/bash

# Wake Word Detection Installation Script for ASTA
# This script installs the required dependencies for wake word detection

set -e

echo "=========================================="
echo "ASTA Wake Word Detection Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"
echo ""

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip."
    exit 1
fi

echo "✅ pip3 found: $(pip3 --version)"
echo ""

# Install core dependencies
echo "📦 Installing core wake word dependencies..."
pip3 install openwakeword tflite-runtime websockets

echo ""
echo "📦 Installing PyAudio (may require system dependencies)..."

# Detect OS and install PyAudio accordingly
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Detected Linux. Installing portaudio19-dev..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y portaudio19-dev
    elif command -v yum &> /dev/null; then
        sudo yum install -y portaudio-devel
    else
        echo "⚠️  Could not detect package manager. Please install portaudio manually."
    fi
    pip3 install PyAudio
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Detected macOS. Installing portaudio via Homebrew..."
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew not found. Please install Homebrew first:"
        echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    brew install portaudio
    pip3 install PyAudio
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "Detected Windows. Installing PyAudio via pipwin..."
    pip3 install pipwin
    pipwin install pyaudio
else
    echo "⚠️  Unknown OS. Attempting to install PyAudio directly..."
    pip3 install PyAudio
fi

echo ""
echo "✅ Dependencies installed successfully!"
echo ""

# Update .env file
echo "📝 Updating .env configuration..."

if [ ! -f .env ]; then
    if [ -f .env.template ]; then
        echo "Creating .env from template..."
        cp .env.template .env
    else
        echo "Creating new .env file..."
        touch .env
    fi
fi

# Check if wake word config already exists
if grep -q "WAKE_WORD_ENABLED" .env; then
    echo "Wake word configuration already exists in .env"
else
    echo "Adding wake word configuration to .env..."
    cat >> .env << EOF

# Wake Word Detection
WAKE_WORD_ENABLED=true
WAKE_WORD_MODELS=hey_jarvis
WAKE_WORD_THRESHOLD=0.5
WAKE_WORD_COOLDOWN=2.0
EOF
fi

echo ""
echo "✅ Configuration updated!"
echo ""

# Run test
echo "🧪 Running wake word detection test..."
echo ""

if python3 test_wake_word.py; then
    echo ""
    echo "=========================================="
    echo "✅ Installation Complete!"
    echo "=========================================="
    echo ""
    echo "Wake word detection is now ready to use."
    echo ""
    echo "Next steps:"
    echo "1. Start ASTA backend:"
    echo "   cd backend && uvicorn app.main:app --reload"
    echo ""
    echo "2. Test with microphone:"
    echo "   python3 test_wake_word.py --mic"
    echo ""
    echo "3. Configure wake word in .env:"
    echo "   - WAKE_WORD_ENABLED=true"
    echo "   - WAKE_WORD_MODELS=hey_jarvis"
    echo "   - WAKE_WORD_THRESHOLD=0.5"
    echo ""
    echo "See WAKE_WORD_SETUP.md for detailed documentation."
    echo ""
else
    echo ""
    echo "⚠️  Test failed. Please check the error messages above."
    echo "See WAKE_WORD_SETUP.md for troubleshooting."
    exit 1
fi
