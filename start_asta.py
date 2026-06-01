#!/usr/bin/env python3
"""
ASTA Startup Script
Automatically detects ngrok URL and updates Android app configuration
"""
import subprocess
import sys
import time
import os
from get_ngrok_url import get_ngrok_url, update_android_config

def check_ngrok_running():
    """Check if ngrok is running"""
    try:
        import requests
        response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=2)
        return response.status_code == 200
    except:
        return False

def start_ngrok():
    """Start ngrok tunnel"""
    print("Starting ngrok tunnel on port 8000...")
    try:
        # Start ngrok in background
        if sys.platform == 'win32':
            subprocess.Popen(['start', 'cmd', '/k', 'ngrok', 'http', '8000'], shell=True)
        else:
            subprocess.Popen(['ngrok', 'http', '8000'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait for ngrok to start
        print("Waiting for ngrok to initialize...")
        for i in range(10):
            time.sleep(1)
            if check_ngrok_running():
                print("✓ ngrok started successfully")
                return True
        
        print("✗ ngrok failed to start")
        return False
    except Exception as e:
        print(f"✗ Error starting ngrok: {e}")
        return False

def start_backend():
    """Start the ASTA backend"""
    print("\nStarting ASTA backend...")
    try:
        if sys.platform == 'win32':
            subprocess.Popen(['start', 'cmd', '/k', 'python', 'run.py'], shell=True)
        else:
            subprocess.Popen(['python3', 'run.py'])
        print("✓ Backend starting...")
        return True
    except Exception as e:
        print(f"✗ Error starting backend: {e}")
        return False

def main():
    print("=" * 60)
    print("ASTA Startup Script")
    print("=" * 60)
    
    # Step 1: Check/Start ngrok
    if not check_ngrok_running():
        print("\nngrok is not running")
        response = input("Would you like to start ngrok? (y/n): ").strip().lower()
        if response == 'y':
            if not start_ngrok():
                print("\nPlease start ngrok manually with: ngrok http 8000")
                sys.exit(1)
        else:
            print("\nPlease start ngrok manually with: ngrok http 8000")
            sys.exit(1)
    else:
        print("\n✓ ngrok is already running")
    
    # Step 2: Get ngrok URL
    print("\nFetching ngrok URL...")
    time.sleep(2)  # Give ngrok a moment to stabilize
    ngrok_url = get_ngrok_url()
    
    if not ngrok_url:
        print("\n✗ Failed to get ngrok URL")
        print("Please check that ngrok is running properly")
        sys.exit(1)
    
    print(f"✓ Found ngrok URL: {ngrok_url}")
    
    # Step 3: Update Android config
    print("\nUpdating Android app configuration...")
    if update_android_config(ngrok_url):
        print("✓ Android app configured successfully")
    else:
        print("✗ Failed to update Android config")
        sys.exit(1)
    
    # Step 4: Start backend
    response = input("\nWould you like to start the backend server? (y/n): ").strip().lower()
    if response == 'y':
        start_backend()
        print("\nWaiting for backend to initialize...")
        time.sleep(5)
    
    # Step 5: Summary
    print("\n" + "=" * 60)
    print("ASTA is ready!")
    print("=" * 60)
    print(f"\nBackend URL: {ngrok_url}")
    print(f"Backend API: {ngrok_url}api/")
    print(f"Health Check: {ngrok_url}api/health")
    print("\nYou can now:")
    print("1. Build and run the Android app")
    print("2. The app will automatically connect to:", ngrok_url)
    print("\nPress Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")

if __name__ == '__main__':
    main()
