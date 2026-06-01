#!/bin/bash
# ASTA Memory Layer Setup Script
# Run this after setting up environment variables

echo "=========================================="
echo "ASTA Memory Layer Setup"
echo "=========================================="
echo ""

# Check environment variables
echo "Checking environment variables..."
if [ -z "$NEO4J_URI" ]; then
    echo "❌ NEO4J_URI not set"
    exit 1
fi
if [ -z "$NEO4J_USERNAME" ]; then
    echo "❌ NEO4J_USERNAME not set"
    exit 1
fi
if [ -z "$NEO4J_PASSWORD" ]; then
    echo "❌ NEO4J_PASSWORD not set"
    exit 1
fi
if [ -z "$MONGODB_URI" ]; then
    echo "❌ MONGODB_URI not set"
    exit 1
fi
if [ -z "$PINECONE_API_KEY" ]; then
    echo "❌ PINECONE_API_KEY not set"
    exit 1
fi
if [ -z "$PINECONE_INDEX_NAME" ]; then
    echo "❌ PINECONE_INDEX_NAME not set"
    exit 1
fi
if [ -z "$GROQ_API_KEY" ]; then
    echo "❌ GROQ_API_KEY not set"
    exit 1
fi

echo "✅ All environment variables set"
echo ""

# Initialize Neo4j schema
echo "Initializing Neo4j schema..."
python -m memory.schema_init

if [ $? -eq 0 ]; then
    echo "✅ Neo4j schema initialized"
else
    echo "❌ Neo4j schema initialization failed"
    exit 1
fi
echo ""

# Run tests
echo "Running memory layer tests..."
python test_memory_layer.py

if [ $? -eq 0 ]; then
    echo "✅ All tests passed"
else
    echo "❌ Tests failed"
    exit 1
fi
echo ""

echo "=========================================="
echo "✅ Memory Layer Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Review MEMORY_INTEGRATION_GUIDE.md"
echo "2. Update backend/app/main.py to start retry worker"
echo "3. Update backend/app/api/ws_routes.py to use new memory layer"
echo "4. Deploy and monitor"
echo ""
