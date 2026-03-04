# Cloud Run — web_server (FastAPI search over output bucket / RAG).
# Same pattern as Old app: Python 3.11, PORT=8080, uvicorn.
FROM python:3.11-slim

ENV PORT=8080
EXPOSE 8080

WORKDIR /app

COPY web_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web_server ./web_server
# Run from web_server so config and app resolve; Cloud Run sets PORT at runtime.
WORKDIR /app/web_server
ENV PYTHONPATH=/app/web_server

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
