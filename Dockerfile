# Phase 1: Cloud Run — Python app with ffmpeg for audio pipeline
FROM python:3.11-slim

# Install ffmpeg and libsndfile for pydub (mp3/mp4/wav)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ENV PORT=8080
EXPOSE 8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sets PORT at runtime; use it so the container listens on the correct port.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
