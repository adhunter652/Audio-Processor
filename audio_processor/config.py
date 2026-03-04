"""Audio processor config: queue location (local folder or GCS)."""
import os
from pathlib import Path

AUDIO_PROCESSOR_DIR = Path(__file__).resolve().parent
UPLOAD_QUEUE_DIR = Path(os.getenv("UPLOAD_QUEUE_DIR", str(AUDIO_PROCESSOR_DIR / "upload_queue")))
UPLOAD_QUEUE_GCS_PREFIX = "upload_queue/"
RUN_CLOUD = os.getenv("RUN_CLOUD", "").strip().lower() in ("1", "true", "yes")
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "10"))
