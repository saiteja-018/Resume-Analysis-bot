FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pdfplumber/Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Health check — verify imports work
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "from config import *; from bot import main; print('ok')" || exit 1

# Run the bot
CMD ["python", "-u", "bot.py"]
