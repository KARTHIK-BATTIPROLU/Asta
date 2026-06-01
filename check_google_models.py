#!/usr/bin/env python3
"""
Check available Google AI models
"""

import google.generativeai as genai
from backend.app.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

print("=== Available Google AI Models ===")
for model in genai.list_models():
    if 'embed' in model.name.lower():
        print(f"Model: {model.name}")
        print(f"  Supported methods: {model.supported_generation_methods}")
        print()