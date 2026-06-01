#!/usr/bin/env python3
"""
ASTA OpenAI API Key Setup
─────────────────────────

This script helps you add your OpenAI API key to the .env file.
You need an OpenAI API key for the memory system to work.

Get your API key from: https://platform.openai.com/api-keys
"""

import os
import sys

def setup_openai_key():
    print("=== ASTA OpenAI API Key Setup ===\n")
    
    # Check if .env exists
    if not os.path.exists('.env'):
        print("ERROR: .env file not found!")
        return False
    
    # Read current .env
    with open('.env', 'r') as f:
        content = f.read()
    
    # Check if OPENAI_API_KEY exists
    if 'OPENAI_API_KEY=' in content:
        if 'sk-placeholder' in content:
            print("Found placeholder OpenAI API key in .env file.")
            print("You need to replace it with your real API key.\n")
        else:
            print("OpenAI API key already configured in .env file.")
            return True
    
    print("To get your OpenAI API key:")
    print("1. Go to https://platform.openai.com/api-keys")
    print("2. Sign in to your OpenAI account")
    print("3. Click 'Create new secret key'")
    print("4. Copy the key (starts with 'sk-')")
    print("5. Replace the placeholder in .env file\n")
    
    key = input("Enter your OpenAI API key (or press Enter to skip): ").strip()
    
    if key and key.startswith('sk-'):
        # Replace the placeholder
        new_content = content.replace(
            'OPENAI_API_KEY=sk-placeholder-add-your-openai-key-here',
            f'OPENAI_API_KEY={key}'
        )
        
        with open('.env', 'w') as f:
            f.write(new_content)
        
        print("✅ OpenAI API key updated in .env file!")
        return True
    else:
        print("⚠️  No valid API key provided. Please update .env manually.")
        return False

if __name__ == "__main__":
    setup_openai_key()