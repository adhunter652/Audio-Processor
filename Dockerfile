# Cloud Run — web_server (FastAPI search over output bucket / RAG).
# Same pattern as Old app: Python 3.11, PORT=8080, uvicorn.
FROM python:3.11-slim

ENV PORT=8080
EXPOSE 8080

WORKDIR /app

COPY web_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the RAG embedding model so instances don't hit Hugging Face at runtime (avoids rate limits).
# Set HF_TOKEN as a build arg if you have one (e.g. --build-arg HF_TOKEN=...) for higher rate limits.
ARG HF_TOKEN=
ENV HF_TOKEN=${HF_TOKEN}
ENV RAG_EMBEDDING_CACHE=/app/embedding_cache
RUN mkdir -p /app/embedding_cache && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', cache_folder='/app/embedding_cache')"

COPY web_server ./web_server
# Run from web_server so config and app resolve; Cloud Run sets PORT at runtime.
WORKDIR /app/web_server
ENV PYTHONPATH=/app/web_server

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
