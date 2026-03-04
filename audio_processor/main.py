"""
Audio processor: standalone service that processes media from a queue and writes results to the output bucket.

- Local: looks for an "upload_queue" folder; processes media files and removes them as they are processed.
- Cloud: checks the uploads bucket upload_queue/ for media; processes, removes from bucket, stores results in output bucket.

Run from repo root so app.pipeline and app.storage are available:
  python -m audio_processor.main
Or: cd audio_processor && set PYTHONPATH=.. && python main.py
"""
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# Ensure repo root is on path for app and config
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import (
    ALLOWED_EXTENSIONS,
    GCS_OUTPUT_BUCKET,
    GCS_UPLOAD_BUCKET,
    OUTPUT_DIR,
)
from app.pipeline.runner import run_pipeline, get_job, persist_job_state
from app.pipeline.steps import ensure_ffmpeg_available
from app.storage import get_upload_path, upload_local_file, delete_local_if_temp

from audio_processor.config import (
    UPLOAD_QUEUE_DIR,
    UPLOAD_QUEUE_GCS_PREFIX,
    RUN_CLOUD,
    POLL_INTERVAL_SEC,
)

logger = logging.getLogger("audio_processor")

# Same layout as main app
JOBS_STATE_DIR = OUTPUT_DIR / "job_state"


def _ensure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.setLevel(logging.INFO)


def _list_local_queue():
    """Return list of (path, original_filename) for allowed media in UPLOAD_QUEUE_DIR."""
    if not UPLOAD_QUEUE_DIR.exists() or not UPLOAD_QUEUE_DIR.is_dir():
        return []
    out = []
    for f in UPLOAD_QUEUE_DIR.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() in ALLOWED_EXTENSIONS:
            out.append((f, f.name))
    return out


def _list_gcs_queue():
    """Return list of (blob_name, original_filename) for media in upload_queue/ in GCS_UPLOAD_BUCKET."""
    if not GCS_UPLOAD_BUCKET:
        return []
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_UPLOAD_BUCKET)
    out = []
    for blob in bucket.list_blobs(prefix=UPLOAD_QUEUE_GCS_PREFIX):
        if blob.name.endswith("/"):
            continue
        suf = Path(blob.name).suffix.lower()
        if suf in ALLOWED_EXTENSIONS:
            # original_filename: use blob name without prefix
            name = blob.name[len(UPLOAD_QUEUE_GCS_PREFIX):]
            out.append((blob.name, name))
    return out


def _download_gcs_to_temp(gcs_uri: str) -> Path:
    """Download gs://bucket/key to a temp file. Caller must delete when done."""
    from app.storage import get_upload_path
    return get_upload_path(gcs_uri)


def _delete_from_gcs_queue(blob_name: str) -> None:
    """Remove blob from upload bucket (after successful process)."""
    if not GCS_UPLOAD_BUCKET:
        return
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_UPLOAD_BUCKET)
    blob = bucket.blob(blob_name)
    try:
        blob.delete()
        logger.info("Deleted from queue: %s", blob_name)
    except Exception as e:
        logger.warning("Failed to delete %s: %s", blob_name, e)


def _upload_wav_to_gcs(job_id: str) -> None:
    """Upload WAV for this job to GCS output bucket (outputs/). job_state is uploaded by persist_job_state."""
    if not GCS_OUTPUT_BUCKET:
        return
    wav_path = OUTPUT_DIR / f"{job_id}_audio.wav"
    if wav_path.exists():
        upload_local_file(
            wav_path,
            f"gs://{GCS_OUTPUT_BUCKET}/outputs/{job_id}_audio.wav",
            content_type="audio/wav",
        )
        logger.info("Uploaded outputs/%s_audio.wav to GCS", job_id)


def process_one_local(path: Path, original_filename: str) -> bool:
    """Process one local file; upload results to GCS if configured; remove file on success. Return True if processed (success or failure)."""
    job_id = str(uuid.uuid4())
    try:
        run_pipeline(path, original_filename, job_id=job_id, file_hash=None, folder_id=None)
        state = get_job(job_id)
        if not state:
            logger.warning("No state for job %s", job_id)
            return True
        persist_job_state(state)
        if state.status == "completed" and GCS_OUTPUT_BUCKET:
            _upload_wav_to_gcs(job_id)
        if state.status in ("completed", "failed", "cancelled"):
            try:
                path.unlink()
                logger.info("Removed from queue: %s", path.name)
            except Exception as e:
                logger.warning("Could not remove %s: %s", path.name, e)
        return True
    except Exception as e:
        logger.exception("Processing failed for %s: %s", path.name, e)
        return True  # consider processed so we don't block queue


def process_one_cloud(blob_name: str, original_filename: str) -> bool:
    """Download from GCS, process, upload results to output bucket, delete from queue. Return True when done (success or failure)."""
    gcs_uri = f"gs://{GCS_UPLOAD_BUCKET}/{blob_name}"
    job_id = str(uuid.uuid4())
    local_path = None
    try:
        local_path = _download_gcs_to_temp(gcs_uri)
        run_pipeline(local_path, original_filename, job_id=job_id, file_hash=None, folder_id=None)
        state = get_job(job_id)
        if not state:
            logger.warning("No state for job %s", job_id)
            return True
        persist_job_state(state)
        if state.status == "completed" and GCS_OUTPUT_BUCKET:
            _upload_wav_to_gcs(job_id)
        _delete_from_gcs_queue(blob_name)
        return True
    except Exception as e:
        logger.exception("Processing failed for %s: %s", blob_name, e)
        return True
    finally:
        if local_path and local_path.exists() and "gcs_upload_" in str(local_path):
            delete_local_if_temp(local_path, was_gcs=True)


def run_local_loop():
    """Process files from local upload_queue directory."""
    UPLOAD_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Local mode: watching %s for media files", UPLOAD_QUEUE_DIR)
    while True:
        items = _list_local_queue()
        if not items:
            time.sleep(POLL_INTERVAL_SEC)
            continue
        path, name = items[0]
        logger.info("Processing: %s", name)
        process_one_local(path, name)


def run_cloud_loop():
    """Process files from GCS upload_queue/ prefix."""
    if not GCS_UPLOAD_BUCKET:
        logger.error("Cloud mode requires GCS_UPLOAD_BUCKET")
        return
    logger.info("Cloud mode: watching gs://%s/%s for media files", GCS_UPLOAD_BUCKET, UPLOAD_QUEUE_GCS_PREFIX)
    while True:
        items = _list_gcs_queue()
        if not items:
            time.sleep(POLL_INTERVAL_SEC)
            continue
        blob_name, original_filename = items[0]
        logger.info("Processing: %s", blob_name)
        process_one_cloud(blob_name, original_filename)


def main():
    _ensure_logging()
    ok, msg = ensure_ffmpeg_available()
    if not ok:
        logger.warning("FFmpeg: %s. Non-WAV files may fail.", msg)
    JOBS_STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Cloud mode: read from GCS upload bucket upload_queue/, write to GCS output bucket
    if RUN_CLOUD or GCS_UPLOAD_BUCKET:
        run_cloud_loop()
    else:
        run_local_loop()


if __name__ == "__main__":
    main()
