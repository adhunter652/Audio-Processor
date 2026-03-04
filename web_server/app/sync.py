"""
Sync RAG with output bucket: if there are new completed jobs in job_state/, index them and update RAG.
Uses indexed_job_ids.json to track what's already indexed so we only re-index new jobs.
"""
import json
import logging
from pathlib import Path

from config import GCS_OUTPUT_BUCKET, INDEXED_JOBS_FILE, RAG_DIR
from app.rag import index_transcript_segments, index_meeting
from app.storage import restore_rag_from_gcs, upload_rag_db_to_gcs

logger = logging.getLogger("web_server.sync")


def _load_indexed_job_ids() -> set[str]:
    """Load set of job_ids already indexed into RAG."""
    if not INDEXED_JOBS_FILE.exists():
        return set()
    try:
        data = json.loads(INDEXED_JOBS_FILE.read_text(encoding="utf-8"))
        ids = data.get("job_ids") if isinstance(data, dict) else data
        return set(ids) if isinstance(ids, list) else set()
    except Exception as e:
        logger.warning("Could not load indexed_job_ids: %s", e)
        return set()


def _save_indexed_job_ids(job_ids: set[str]) -> None:
    """Persist indexed job_ids to RAG_DIR so we don't re-index on next run."""
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    INDEXED_JOBS_FILE.write_text(
        json.dumps({"job_ids": sorted(job_ids)}, indent=2),
        encoding="utf-8",
    )


def _merge_new_jobs_from_bucket(progress_callback=None):
    """
    List job_state/*.json from GCS output bucket; for each completed job not yet in indexed set,
    index into RAG. Returns (indexed_count, errors).
    progress_callback: optional callable(message: str) for progress updates.
    """
    if not GCS_OUTPUT_BUCKET:
        return 0, []
    from google.cloud import storage
    prefix = "job_state/"
    bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
    indexed_ids = _load_indexed_job_ids()
    if progress_callback:
        progress_callback("Listing jobs in bucket…")
    blobs = list(bucket.list_blobs(prefix=prefix))
    job_blobs = [b for b in blobs if b.name.endswith(".json")]
    to_index = []
    for blob in job_blobs:
        job_id = blob.name[len(prefix):-5]
        if not job_id or job_id in indexed_ids:
            continue
        to_index.append((blob, job_id))
    if progress_callback:
        progress_callback(f"Found {len(to_index)} new job(s) to index.")
    newly_indexed = 0
    errors = []
    for i, (blob, job_id) in enumerate(to_index, 1):
        if progress_callback:
            progress_callback(f"Indexing job {i}/{len(to_index)}: {job_id}")
        try:
            data = json.loads(blob.download_as_string().decode("utf-8"))
        except Exception as e:
            errors.append(f"{blob.name}: {e}")
            continue
        if data.get("status") != "completed":
            continue
        result = data.get("result") or {}
        timestamps = result.get("timestamps") or []
        main_topic = (result.get("main_topic") or "").strip()
        subtopics = result.get("subtopics") or []
        original_filename = (result.get("original_filename") or data.get("original_filename") or job_id).strip()
        folder_id = data.get("folder_id")
        if folder_id is not None and not isinstance(folder_id, int):
            try:
                folder_id = int(folder_id)
            except (TypeError, ValueError):
                folder_id = None
        try:
            if timestamps:
                index_transcript_segments(
                    job_id=job_id,
                    timestamps=timestamps,
                    original_filename=original_filename,
                    folder_id=folder_id,
                )
            if main_topic or subtopics:
                index_meeting(
                    job_id=job_id,
                    original_filename=original_filename,
                    main_topic=main_topic,
                    subtopics=subtopics if isinstance(subtopics, list) else [],
                    folder_id=folder_id,
                )
            indexed_ids.add(job_id)
            newly_indexed += 1
        except Exception as e:
            errors.append(f"{job_id}: {e}")
    if newly_indexed > 0:
        _save_indexed_job_ids(indexed_ids)
    return newly_indexed, errors


def ensure_rag_synced_with_bucket(progress_callback=None) -> tuple[bool, int, list[str]]:
    """
    On startup: restore RAG from bucket if rag_db/latest.zip exists; then merge any new completed
    jobs from job_state/ into RAG; if we indexed any, upload updated RAG to bucket.
    Returns (restored_from_bucket, newly_indexed_count, errors).
    progress_callback: optional callable(message: str) for progress updates.
    """
    def progress(msg):
        if progress_callback:
            progress_callback(msg)
        logger.info("%s", msg)

    if not GCS_OUTPUT_BUCKET:
        progress("No output bucket configured; nothing to sync.")
        return False, 0, []

    restored = False
    if GCS_OUTPUT_BUCKET:
        try:
            from google.cloud import storage
            progress("Checking for existing RAG in bucket…")
            bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
            blob = bucket.blob("rag_db/latest.zip")
            if blob.exists():
                progress("Restoring RAG from bucket (rag_db/latest.zip)…")
                if restore_rag_from_gcs(GCS_OUTPUT_BUCKET, "rag_db/latest.zip"):
                    restored = True
                    progress("RAG restored from bucket.")
                else:
                    progress("RAG restore failed.")
            else:
                progress("No existing RAG in bucket; starting fresh.")
        except Exception as e:
            logger.warning("Could not restore RAG from bucket: %s", e)
            if progress_callback:
                progress_callback(f"Could not restore RAG: {e}")
    newly_indexed, errors = _merge_new_jobs_from_bucket(progress_callback=progress_callback)
    if errors:
        logger.warning("Merge had %d errors: %s", len(errors), errors[:3])
        if progress_callback:
            progress_callback(f"Encountered {len(errors)} error(s) while indexing.")
    if newly_indexed > 0 and GCS_OUTPUT_BUCKET:
        if progress_callback:
            progress_callback("Uploading updated RAG to bucket…")
        upload_rag_db_to_gcs(GCS_OUTPUT_BUCKET, prefix="rag_db")
        if progress_callback:
            progress_callback("Upload complete.")
    return restored, newly_indexed, errors
