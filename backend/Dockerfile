FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
# CPU-only torch wheel first (default PyPI wheel pulls CUDA libs — huge and unneeded on Render)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browser for web scraping
RUN playwright install chromium

# Copy application code (build context is the repo root)
COPY . .

# Expose port (Render injects $PORT at runtime; default 8000 for local docker run)
EXPOSE 8000

# Run the application (backend.app.* imports + top-level memory/ both resolve here)
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]