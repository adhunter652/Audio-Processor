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


def _merge_new_jobs_from_bucket() -> tuple[int, list[str]]:
    """
    List job_state/*.json from GCS output bucket; for each completed job not yet in indexed set,
    index into RAG. Returns (indexed_count, errors).
    """
    if not GCS_OUTPUT_BUCKET:
        return 0, []
    from google.cloud import storage
    prefix = "job_state/"
    bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
    indexed_ids = _load_indexed_job_ids()
    newly_indexed = 0
    errors = []
    for blob in bucket.list_blobs(prefix=prefix):
        if not blob.name.endswith(".json"):
            continue
        job_id = blob.name[len(prefix):-5]
        if not job_id or job_id in indexed_ids:
            continue
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


def ensure_rag_synced_with_bucket() -> tuple[bool, int, list[str]]:
    """
    On startup: restore RAG from bucket if rag_db/latest.zip exists; then merge any new completed
    jobs from job_state/ into RAG; if we indexed any, upload updated RAG to bucket.
    Returns (restored_from_bucket, newly_indexed_count, errors).
    """
    restored = False
    if GCS_OUTPUT_BUCKET:
        try:
            from google.cloud import storage
            bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
            blob = bucket.blob("rag_db/latest.zip")
            if blob.exists():
                logger.info("Restoring RAG from bucket (rag_db/latest.zip)...")
                if restore_rag_from_gcs(GCS_OUTPUT_BUCKET, "rag_db/latest.zip"):
                    restored = True
                    logger.info("RAG restored from bucket")
        except Exception as e:
            logger.warning("Could not restore RAG from bucket: %s", e)
    newly_indexed, errors = _merge_new_jobs_from_bucket()
    if errors:
        logger.warning("Merge had %d errors: %s", len(errors), errors[:3])
    if newly_indexed > 0 and GCS_OUTPUT_BUCKET:
        upload_rag_db_to_gcs(GCS_OUTPUT_BUCKET, prefix="rag_db")
    return restored, newly_indexed, errors
