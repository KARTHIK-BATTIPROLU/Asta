"""
Extract OpenWakeWord ONNX models for Android integration.
This script downloads/locates the models and copies them to Android assets folder.
"""
import os
import shutil
import sys

def extract_models():
    """Extract OpenWakeWord models to Android assets."""
    
    print("=" * 60)
    print("OpenWakeWord Model Extractor for Android")
    print("=" * 60)
    
    # Check if openwakeword is installed
    try:
        import openwakeword
        from openwakeword.model import Model
        print("✅ openwakeword library found")
    except ImportError:
        print("❌ openwakeword not installed")
        print("\nInstall with: pip install openwakeword")
        return False
    
    # Initialize model (this will download models if needed)
    print("\n📥 Initializing OpenWakeWord model...")
    try:
        model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        print("✅ Model initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize model: {e}")
        return False
    
    # Find models directory
    models_dir = os.path.join(
        os.path.dirname(openwakeword.__file__),
        "resources",
        "models"
    )
    
    if not os.path.exists(models_dir):
        print(f"❌ Models directory not found: {models_dir}")
        return False
    
    print(f"✅ Models directory: {models_dir}")
    
    # Define source and destination paths
    melspec_src = os.path.join(models_dir, "melspectrogram.onnx")
    wakeword_src = os.path.join(models_dir, "hey_jarvis_v0.1.onnx")  # Updated filename
    
    # Check if models exist
    if not os.path.exists(melspec_src):
        print(f"❌ Melspectrogram model not found: {melspec_src}")
        return False
    
    if not os.path.exists(wakeword_src):
        print(f"❌ Wake word model not found: {wakeword_src}")
        return False
    
    print(f"✅ Found melspectrogram.onnx ({os.path.getsize(melspec_src) / 1024:.1f} KB)")
    print(f"✅ Found hey_jarvis.onnx ({os.path.getsize(wakeword_src) / 1024:.1f} KB)")
    
    # Create Android assets directory
    android_assets = os.path.join("ASTA MOBILE", "app", "src", "main", "assets")
    os.makedirs(android_assets, exist_ok=True)
    print(f"\n📁 Android assets directory: {android_assets}")
    
    # Copy models
    print("\n📋 Copying models...")
    try:
        melspec_dst = os.path.join(android_assets, "melspectrogram.onnx")
        wakeword_dst = os.path.join(android_assets, "hey_jarvis.onnx")
        
        shutil.copy2(melspec_src, melspec_dst)
        print(f"✅ Copied melspectrogram.onnx")
        
        shutil.copy2(wakeword_src, wakeword_dst)
        print(f"✅ Copied hey_jarvis.onnx")
        
    except Exception as e:
        print(f"❌ Failed to copy models: {e}")
        return False
    
    # Verify copied files
    print("\n🔍 Verifying copied files...")
    if os.path.exists(melspec_dst) and os.path.exists(wakeword_dst):
        print(f"✅ melspectrogram.onnx: {os.path.getsize(melspec_dst) / 1024:.1f} KB")
        print(f"✅ hey_jarvis.onnx: {os.path.getsize(wakeword_dst) / 1024:.1f} KB")
    else:
        print("❌ Verification failed")
        return False
    
    print("\n" + "=" * 60)
    print("✅ SUCCESS! Models extracted to Android assets")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Implement ONNX inference in OpenWakeWordEngine.kt")
    print("2. Build and test the Android app")
    print("3. See ANDROID_OPENWAKEWORD_SETUP.md for details")
    
    return True


if __name__ == "__main__":
    success = extract_models()
    sys.exit(0 if success else 1)
