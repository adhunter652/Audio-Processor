"""Web server configuration: output bucket, RAG, and search only."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    # Load from web_server/.env so config is self-contained (local dev or run from repo root)
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass
# Output bucket: job_state/, outputs/, rag_db/ (same structure)
GCS_OUTPUT_BUCKET = os.getenv("GCS_OUTPUT_BUCKET", "")
GCS_SIGNING_KEY_JSON = os.getenv("GCS_SIGNING_KEY_JSON", "").strip()

# RAG: local embedding model and vector DB path
RAG_DIR = BASE_DIR / "rag_db"
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
# Persistent cache for the embedding model (avoids re-downloading from Hugging Face every run/instance)
RAG_EMBEDDING_CACHE = os.getenv("RAG_EMBEDDING_CACHE") or str(RAG_DIR / "embedding_model_cache")
RAG_SEARCH_LIMIT = int(os.getenv("RAG_SEARCH_LIMIT", "20"))

# Track which job_ids have been indexed (so we only re-index new jobs)
INDEXED_JOBS_FILE = RAG_DIR / "indexed_job_ids.json"

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("PORT") or os.getenv("SERVER_PORT", "8000"))
