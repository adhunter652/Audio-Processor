"""Pipeline service config: read from env (server sets these at startup when running in same process)."""
import os
from pathlib import Path

_OUTPUT_DEFAULT = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(_OUTPUT_DEFAULT)))
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "distil-whisper/distil-large-v3")
LLM_MODEL_NAME = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
LLM_MAX_INPUT_TOKENS = int(os.getenv("LLM_MAX_INPUT_TOKENS", "2048"))
LLM_CHUNK_TRANSCRIPT_TOKENS = int(os.getenv("LLM_CHUNK_TRANSCRIPT_TOKENS", "1536"))
LLM_REPETITION_PENALTY = float(os.getenv("LLM_REPETITION_PENALTY", "1.1"))
