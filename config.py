"""Application configuration. All models from Hugging Face, run locally."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Paths
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Pipeline limits (from project-overview: file size threshold)
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".mp4"}

# Hugging Face models (run locally)

# ASR: distil-whisper (project-overview)
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "distil-whisper/distil-large-v3")

# LLM: instruction-following model for topic and truth-statement extraction
# Default is small so it can run on CPU / limited GPU; override with HF model id.
LLM_MODEL_NAME = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
LLM_MAX_INPUT_TOKENS = int(os.getenv("LLM_MAX_INPUT_TOKENS", "2048"))
# Chunked extraction for long transcripts (tokens of transcript per chunk; prompt uses the rest)
LLM_CHUNK_TRANSCRIPT_TOKENS = int(os.getenv("LLM_CHUNK_TRANSCRIPT_TOKENS", "1536"))
LLM_REPETITION_PENALTY = float(os.getenv("LLM_REPETITION_PENALTY", "1.1"))

# SQL database (folders, job metadata for folder assignment and search filter)
DATABASE_PATH = BASE_DIR / "data" / "app.db"

# RAG: local embedding model and vector DB path
RAG_DIR = BASE_DIR / "rag_db"
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
RAG_SEARCH_LIMIT = int(os.getenv("RAG_SEARCH_LIMIT", "20"))

# Server: bind address and port (0.0.0.0 = all interfaces, accessible from LAN)
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
