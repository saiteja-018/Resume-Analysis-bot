FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pdfplumber/Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Render injects PORT env var; default to 10000
ENV PORT=10000
EXPOSE ${PORT}

# Health check using the actual HTTP endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the bot (unbuffered output for real-time logs)
CMD ["python", "-u", "bot.py"]
