FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browser for web scraping
RUN playwright install chromium

# Copy application code (build context is the repo root)
COPY . .

# Expose port
EXPOSE 8000

# Run the application (backend.app.* imports + top-level memory/ both resolve here)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]