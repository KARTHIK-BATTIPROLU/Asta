#!/usr/bin/env python3
"""
Debug embedding format
"""

import google.generativeai as genai
from backend.app.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

result = genai.embed_content(
    model="models/gemini-embedding-001",
    content="test text",
    task_type="retrieval_document"
)

print(f"Result type: {type(result)}")
print(f"Result keys: {result.keys()}")
print(f"Embedding type: {type(result['embedding'])}")
print(f"First embedding value type: {type(result['embedding'][0])}")
print(f"First 3 values: {result['embedding'][:3]}")

# Test conversion to list of floats
embedding_list = [float(x) for x in result['embedding']]
print(f"Converted type: {type(embedding_list)}")
print(f"Converted first value type: {type(embedding_list[0])}")