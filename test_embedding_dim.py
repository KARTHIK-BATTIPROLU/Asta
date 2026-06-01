#!/usr/bin/env python3
"""
Test Google embedding dimensions
"""

import google.generativeai as genai
from backend.app.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

result = genai.embed_content(
    model="models/gemini-embedding-001",
    content="test text",
    task_type="retrieval_document"
)

print(f"Embedding dimension: {len(result['embedding'])}")
print(f"First 5 values: {result['embedding'][:5]}")