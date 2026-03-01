"""Data contracts at pipeline boundaries and intermediate statistics logging.

Contracts align with docs/assignment2-pipeline-architecture.md.
"""
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("audio_pipeline.contracts")

# Contract version identifiers (for observability and compatibility)
PREPROCESS_CONTRACT_VERSION = "preprocess_v1"
TRANSCRIBE_CONTRACT_VERSION = "transcribe_v1"
LLM_ANALYZE_CONTRACT_VERSION = "llm_analyze_v1"


def validate_upload_input(file_path: Path, size_bytes: int, allowed_extensions: set, max_size_bytes: int) -> None:
    """Validation → Transformation boundary: input must match upload contract."""
    suf = file_path.suffix.lower()
    if suf not in allowed_extensions:
        raise ValueError(f"Invalid extension: {suf}. Allowed: {allowed_extensions}")
    if size_bytes < 1 or size_bytes > max_size_bytes:
        raise ValueError(f"File size {size_bytes} out of range [1, {max_size_bytes}]")
    if not file_path.exists():
        raise FileNotFoundError(f"Upload path does not exist: {file_path}")


def validate_preprocess_output(audio_path: Path | None) -> None:
    """Transformation → Representation boundary: preprocess must produce a WAV path."""
    if audio_path is None:
        raise ValueError("Preprocess contract violation: audio_path is None")
    if not isinstance(audio_path, Path):
        raise TypeError("Preprocess contract violation: audio_path must be Path")
    if not audio_path.exists():
        raise FileNotFoundError(f"Preprocess contract violation: WAV file missing: {audio_path}")


def validate_transcribe_output(transcription: str, timestamps: list) -> None:
    """Representation → Model Inference (LLM): transcribe output shape and types."""
    if not isinstance(transcription, str):
        raise TypeError("Transcribe contract violation: transcription must be str")
    if not isinstance(timestamps, list):
        raise TypeError("Transcribe contract violation: timestamps must be list")
    for i, seg in enumerate(timestamps):
        if not isinstance(seg, dict):
            raise TypeError(f"Transcribe contract violation: timestamps[{i}] must be dict")
        for key in ("start", "end", "text"):
            if key not in seg:
                raise ValueError(f"Transcribe contract violation: segment missing key '{key}'")
        if not (isinstance(seg["start"], (int, float)) and isinstance(seg["end"], (int, float))):
            raise TypeError("Transcribe contract violation: start/end must be numeric")
        if seg["start"] > seg["end"]:
            raise ValueError(f"Transcribe contract violation: start > end in segment {i}")


def validate_llm_input(transcript: str, max_chars: int) -> None:
    """Representation → Model Inference: transcript string fit for LLM (basic)."""
    if not isinstance(transcript, str):
        raise TypeError("LLM input contract violation: transcript must be str")
    if len(transcript) > max_chars:
        raise ValueError(f"LLM input contract violation: transcript length {len(transcript)} > {max_chars}")


def log_intermediate_stats(stage: str, job_id: str, **kwargs: Any) -> None:
    """Log intermediate statistics for observability (boundary protection and thresholds)."""
    # Build a small dict of metrics; in production this could go to a metrics backend
    parts = [f"job_id={job_id}", f"stage={stage}"]
    for k, v in kwargs.items():
        if v is not None:
            parts.append(f"{k}={v}")
    logger.info("pipeline_stats %s", " ".join(parts))
