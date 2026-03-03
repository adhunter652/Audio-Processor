"""FastAPI app: upload, status, results, folders, and search."""
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.config import (
    ALLOWED_EXTENSIONS,
    BASE_DIR,
    GCS_OUTPUT_BUCKET,
    GCS_SIGNING_KEY_JSON,
    GCS_UPLOAD_BUCKET,
    MAX_FILE_SIZE_BYTES,
    OUTPUT_DIR,
    RAG_SEARCH_LIMIT,
    UPLOAD_DIR,
)
from server.app.db import init_db, list_folders, create_folder, update_folder, delete_folder
from server.app.pipeline.runner import (
    get_job,
    get_queue_state,
    add_to_queue,
    remove_from_queue,
    remove_job,
    cancel_job,
    pause_queue,
    resume_queue,
    is_duplicate_in_queue,
    is_already_processed,
    start_queue_worker,
)
from pipeline_service.pipeline import ensure_ffmpeg_available
from server.app.rag import index_meeting, index_transcript_segments, search_transcript_segments, search_meetings
from server.app.storage import (
    upload_local_file,
    upload_rag_db_to_gcs,
    upload_rag_zip_to_gcs,
    upload_output_zip_to_gcs,
    restore_rag_from_gcs,
    restore_rag_from_zip_path,
)

logger = logging.getLogger("audio_pipeline")
app = FastAPI(title="Audio Processing Pipeline", description="Upload audio → transcribe → topics & truth statements")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_pipeline_logging():
    """Ensure audio_pipeline loggers emit INFO to the console (for timing diagnostics)."""
    log = logging.getLogger("audio_pipeline")
    log.setLevel(logging.INFO)
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        log.addHandler(h)


def _merge_rag_from_bucket() -> tuple[int, list[str]]:
    """Re-index job_state/*.json from GCS output bucket into local RAG. Returns (indexed_count, errors)."""
    import json
    from google.cloud import storage
    prefix = "job_state/"
    bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
    indexed = 0
    errors = []
    for blob in bucket.list_blobs(prefix=prefix):
        if not blob.name.endswith(".json"):
            continue
        job_id = blob.name[len(prefix):-5]
        if not job_id:
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
            indexed += 1
        except Exception as e:
            errors.append(f"{job_id}: {e}")
    return indexed, errors


def _restore_rag_from_bucket_if_present() -> None:
    """If GCS output bucket has rag_db/latest.zip, restore it into local RAG so server uses merged index on startup."""
    if not GCS_OUTPUT_BUCKET:
        return
    try:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
        blob = bucket.blob("rag_db/latest.zip")
        if blob.exists():
            logger.info("Startup (background): restoring RAG from bucket (rag_db/latest.zip)...")
            ok = restore_rag_from_gcs(GCS_OUTPUT_BUCKET, "rag_db/latest.zip")
            if ok:
                logger.info("Startup (background): RAG restored from bucket")
            else:
                logger.warning("Startup (background): RAG restore from bucket failed")
        else:
            logger.info("Startup (background): no rag_db/latest.zip in bucket, using local RAG only")
    except Exception as e:
        logger.warning("Startup (background): could not restore RAG from bucket: %s", e)


def _run_startup_tasks():
    """Run DB init, RAG restore from bucket, ffmpeg check, and queue worker in a background thread so the server can bind to PORT immediately (required for Cloud Run)."""
    # Set env so pipeline_service.config uses server paths and model names
    os.environ.setdefault("OUTPUT_DIR", str(OUTPUT_DIR))
    from server.config import WHISPER_MODEL_NAME, LLM_MODEL_NAME, LLM_MAX_INPUT_TOKENS, LLM_CHUNK_TRANSCRIPT_TOKENS, LLM_REPETITION_PENALTY
    os.environ.setdefault("WHISPER_MODEL", WHISPER_MODEL_NAME)
    os.environ.setdefault("LLM_MODEL", LLM_MODEL_NAME)
    os.environ.setdefault("LLM_MAX_INPUT_TOKENS", str(LLM_MAX_INPUT_TOKENS))
    os.environ.setdefault("LLM_CHUNK_TRANSCRIPT_TOKENS", str(LLM_CHUNK_TRANSCRIPT_TOKENS))
    os.environ.setdefault("LLM_REPETITION_PENALTY", str(LLM_REPETITION_PENALTY))

    _ensure_pipeline_logging()
    t0 = time.perf_counter()
    logger.info("Startup (background): initializing database...")
    init_db()
    logger.info("Startup (background): init_db took %.3fs", time.perf_counter() - t0)
    t1 = time.perf_counter()
    _restore_rag_from_bucket_if_present()
    logger.info("Startup (background): RAG restore check took %.3fs", time.perf_counter() - t1)
    t2 = time.perf_counter()
    ok, msg = ensure_ffmpeg_available()
    if not ok:
        logging.getLogger("uvicorn.error").warning(
            "FFmpeg not available: %s Pipeline will fail for .mp3/.mp4 uploads. WAV may still work.", msg
        )
    logger.info("Startup (background): check_ffmpeg took %.3fs", time.perf_counter() - t2)
    t3 = time.perf_counter()
    logger.info("Startup (background): starting queue worker (persisted jobs will load in worker thread)...")
    start_queue_worker()
    logger.info("Startup (background): start_queue_worker took %.3fs (worker runs in background)", time.perf_counter() - t3)
    logger.info("Startup (background): total %.3fs — ready. Models (Whisper/LLM) load on first job.", time.perf_counter() - t0)


@app.on_event("startup")
def startup_ffmpeg_check():
    """Start the server quickly so Cloud Run sees the port listening; run DB/ffmpeg/worker in a background thread."""
    import threading
    t = threading.Thread(target=_run_startup_tasks, daemon=True)
    t.start()
    logger.info("Startup: server binding to port; DB/ffmpeg/worker initializing in background.")

# Serve static assets if we add any
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _validate_file(filename: str, size: int) -> None:
    suf = Path(filename).suffix.lower()
    if suf not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}")
    if size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(400, f"File too large. Max size: {MAX_FILE_SIZE_BYTES // (1024*1024)} MB")


def _file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


_index_html: str | None = None


@app.get("/api/config")
async def api_config():
    """Return client config (e.g. whether to use direct GCS upload and output bucket for export)."""
    return {
        "gcs_upload": bool(GCS_UPLOAD_BUCKET),
        "gcs_output_bucket": bool(GCS_OUTPUT_BUCKET),
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the web UI (cached so first load is fast)."""
    t0 = time.perf_counter()
    global _index_html
    if _index_html is None:
        logger.info("Index: reading index.html from disk (first request)...")
        html_path = BASE_DIR / "templates" / "index.html"
        if not html_path.exists():
            raise HTTPException(404, "index.html not found")
        _index_html = html_path.read_text(encoding="utf-8")
        logger.info("Index: cached index.html in %.3fs", time.perf_counter() - t0)
    else:
        elapsed = time.perf_counter() - t0
        if elapsed > 0.05:
            logger.info("Index: served cached HTML in %.3fs", elapsed)
    return HTMLResponse(content=_index_html)


def _content_type_for_extension(suffix: str) -> str:
    """Return Content-Type for allowed audio/video extensions."""
    suf = (suffix or "").lower()
    if suf == ".mp3":
        return "audio/mpeg"
    if suf == ".wav":
        return "audio/wav"
    if suf == ".mp4":
        return "video/mp4"
    return "application/octet-stream"


def _gcs_client_for_signing():
    """Return a storage Client that can generate signed URLs (requires a private key).
    On Cloud Run, set GCS_SIGNING_KEY_JSON to the service account key JSON."""
    from google.cloud import storage
    if GCS_SIGNING_KEY_JSON:
        import json
        from google.oauth2 import service_account
        try:
            info = json.loads(GCS_SIGNING_KEY_JSON)
        except json.JSONDecodeError as e:
            raise ValueError("GCS_SIGNING_KEY_JSON is not valid JSON") from e
        creds = service_account.Credentials.from_service_account_info(info)
        return storage.Client(credentials=creds, project=info.get("project_id"))
    return storage.Client()


@app.post("/api/upload-url")
async def upload_url(
    filename: str = Form(...),
    size: int = Form(...),
    folder_id: str | None = Form(default=None),
):
    """Generate a V4 signed URL for direct PUT upload to GCS. Requires GCS_UPLOAD_BUCKET to be set."""
    if not GCS_UPLOAD_BUCKET:
        raise HTTPException(503, "Direct upload to cloud is not configured (GCS_UPLOAD_BUCKET)")
    _validate_file(filename, size)
    stem = Path(filename).stem
    suf = Path(filename).suffix or ".mp3"
    object_name = f"uploads/{uuid.uuid4().hex[:12]}_{stem}{suf}"
    content_type = _content_type_for_extension(suf)
    try:
        from google.cloud import storage
        import datetime
        client = _gcs_client_for_signing()
        bucket = client.bucket(GCS_UPLOAD_BUCKET)
        blob = bucket.blob(object_name)
        upload_url_val = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="PUT",
            content_type=content_type,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to generate signed URL: {e}")
    gcs_uri = f"gs://{GCS_UPLOAD_BUCKET}/{object_name}"
    return {
        "upload_url": upload_url_val,
        "object_name": object_name,
        "gcs_uri": gcs_uri,
        "content_type": content_type,
    }


@app.post("/api/queue/enqueue")
async def enqueue_from_gcs(
    object_name: str = Form(...),
    original_filename: str = Form(...),
    folder_id: str | None = Form(default=None),
    file_hash: str | None = Form(default=None),
):
    """Add a file already uploaded to GCS to the pipeline queue. Call after PUT to the signed URL."""
    if not GCS_UPLOAD_BUCKET:
        raise HTTPException(503, "Direct upload to cloud is not configured (GCS_UPLOAD_BUCKET)")
    _validate_file(original_filename, 0)  # size not known; extension check only
    fid: int | None = None
    if folder_id and str(folder_id).strip():
        try:
            fid = int(folder_id)
        except ValueError:
            pass
    gcs_uri = f"gs://{GCS_UPLOAD_BUCKET}/{object_name.lstrip('/')}"
    warnings = []
    if file_hash:
        if is_duplicate_in_queue(file_hash):
            warnings.append("Duplicate file already in queue")
        if is_already_processed(file_hash):
            warnings.append("File was already processed previously")
    queue_id = add_to_queue(gcs_uri, original_filename, file_hash or "", folder_id=fid)
    return {
        "original_filename": original_filename,
        "queue_id": queue_id,
        "folder_id": fid,
        "warnings": warnings if warnings else None,
    }


@app.post("/api/upload")
async def upload(
    files: list[UploadFile] = File(..., description="One or more audio/video files"),
    folder_id: str | None = Form(default=None),
):
    """Upload one or more audio/video files; each is added to the queue. Streams to disk and hashes incrementally so large files don't block memory."""
    if not files:
        raise HTTPException(400, "No files provided")
    fid: int | None = None
    if folder_id and str(folder_id).strip():
        try:
            fid = int(folder_id)
        except ValueError:
            pass
    results = []
    for file in files:
        filename = file.filename or "audio"
        # Unique path per upload so concurrent uploads (e.g. from multiple clients) never collide
        stem = Path(filename).stem
        suf = Path(filename).suffix or ".mp3"
        upload_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}_{stem}{suf}"
        # Stream to disk and validate size / hash incrementally (avoids loading full file into memory)
        total = 0
        try:
            with open(upload_path, "wb") as out:
                h = hashlib.sha256()
                chunk_size = 65536
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_FILE_SIZE_BYTES:
                        out.close()
                        upload_path.unlink(missing_ok=True)
                        raise HTTPException(400, f"File too large. Max size: {MAX_FILE_SIZE_BYTES // (1024*1024)} MB")
                    h.update(chunk)
                    out.write(chunk)
            fhash = h.hexdigest()
        except HTTPException:
            raise
        except Exception as e:
            upload_path.unlink(missing_ok=True)
            raise HTTPException(500, str(e))
        # Re-validate extension (size already checked during stream)
        suf_lower = Path(filename).suffix.lower()
        if suf_lower not in ALLOWED_EXTENSIONS:
            upload_path.unlink(missing_ok=True)
            raise HTTPException(400, f"Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}")
        warnings = []
        if is_duplicate_in_queue(fhash):
            warnings.append("Duplicate file already in queue")
        if is_already_processed(fhash):
            warnings.append("File was already processed previously")
        queue_id = add_to_queue(upload_path, filename, fhash, folder_id=fid)
        results.append({
            "original_filename": file.filename,
            "queue_id": queue_id,
            "folder_id": fid,
            "warnings": warnings if warnings else None,
        })
    return {"results": results}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    """Get pipeline status and step states for a job."""
    state = get_job(job_id)
    if not state:
        raise HTTPException(404, "Job not found")
    return state.to_dict()


@app.get("/api/result/{job_id}")
async def result(job_id: str):
    """Get full result (transcription, topic, subtopics, truth statements) when completed."""
    state = get_job(job_id)
    if not state:
        raise HTTPException(404, "Job not found")
    if state.status != "completed":
        return {"job_id": job_id, "status": state.status, "result": None, "steps": state.to_dict().get("steps")}
    return {"job_id": job_id, "status": state.status, "result": state.result}


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs (for UI)."""
    return get_queue_state()["jobs"]


@app.get("/api/queue")
async def api_get_queue():
    """Get full queue state: paused, current_job_id, pending items, and all jobs."""
    t0 = time.perf_counter()
    state = get_queue_state()
    elapsed = time.perf_counter() - t0
    n_jobs = len(state.get("jobs") or [])
    n_pending = len(state.get("pending") or [])
    logger.info("GET /api/queue: %d jobs, %d pending — %.3fs", n_jobs, n_pending, elapsed)
    if elapsed > 0.2:
        logger.warning(
            "GET /api/queue was slow (%.3fs). If worker is loading persisted jobs, it holds the queue lock until done.",
            elapsed,
        )
    return state


@app.delete("/api/queue/pending/{queue_id}")
async def api_remove_pending(queue_id: str):
    """Remove a pending file from the queue."""
    if not remove_from_queue(queue_id):
        raise HTTPException(404, "Pending item not found or already started")
    return {"ok": True}


@app.delete("/api/job/{job_id}")
async def api_remove_job(job_id: str):
    """Remove a job from the list (completed, failed, or cancelled)."""
    if not remove_job(job_id):
        raise HTTPException(404, "Job not found")
    return {"ok": True}


@app.post("/api/job/{job_id}/cancel")
async def api_cancel_job(job_id: str):
    """Request cancellation of a running job (stops between pipeline steps)."""
    if not cancel_job(job_id):
        raise HTTPException(404, "Job not found or not running")
    return {"ok": True}


@app.post("/api/queue/pause")
async def api_pause_queue():
    """Pause the queue; current job will finish, no new jobs will start."""
    pause_queue()
    return {"ok": True, "paused": True}


@app.post("/api/queue/resume")
async def api_resume_queue():
    """Resume the queue."""
    resume_queue()
    return {"ok": True, "paused": False}


@app.post("/api/upload-rag")
async def api_upload_rag(
    output_file: UploadFile | None = File(default=None),
    rag_file: UploadFile | None = File(default=None),
):
    """
    Upload RAG and/or output archives to the bucket, then auto-update from local if jobs were processed locally.
    Optional: output_file = zip of outputs/ + job_state/; rag_file = zip of rag_db.
    Always syncs local completed job outputs and local RAG to the bucket when available.
    """
    if not GCS_OUTPUT_BUCKET:
        raise HTTPException(503, "GCS output bucket is not configured (GCS_OUTPUT_BUCKET)")
    import tempfile
    JOBS_STATE_DIR = OUTPUT_DIR / "job_state"
    uploaded_rag = None
    latest_rag = None
    uploaded_outputs = []
    from_archive_outputs = []

    if output_file and output_file.filename and output_file.filename.strip():
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(await output_file.read())
                tmp_path = Path(tmp.name)
            try:
                from_archive_outputs = upload_output_zip_to_gcs(GCS_OUTPUT_BUCKET, tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Upload output zip to GCS failed: %s", e)

    rag_file_path = None
    if rag_file and rag_file.filename and rag_file.filename.strip():
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(await rag_file.read())
                rag_file_path = Path(tmp.name)
            uploaded_rag, latest_rag = upload_rag_zip_to_gcs(GCS_OUTPUT_BUCKET, rag_file_path, prefix="rag_db")
            restore_rag_from_zip_path(rag_file_path)
        except Exception as e:
            logger.warning("Upload or restore RAG zip failed: %s", e)
        finally:
            if rag_file_path:
                rag_file_path.unlink(missing_ok=True)

    if output_file and output_file.filename and output_file.filename.strip():
        merge_indexed, merge_errors = _merge_rag_from_bucket()
        if merge_errors:
            logger.warning("Merge RAG from bucket had %d errors: %s", len(merge_errors), merge_errors[:3])

    uploaded_rag, latest_rag = upload_rag_db_to_gcs(GCS_OUTPUT_BUCKET, prefix="rag_db")

    state = get_queue_state()
    completed = [j for j in (state.get("jobs") or []) if j.get("status") == "completed"]
    for j in completed:
        job_id = j.get("job_id")
        if not job_id:
            continue
        wav_path = OUTPUT_DIR / f"{job_id}_audio.wav"
        if wav_path.exists():
            try:
                upload_local_file(
                    wav_path,
                    f"gs://{GCS_OUTPUT_BUCKET}/outputs/{job_id}_audio.wav",
                    content_type="audio/wav",
                )
                uploaded_outputs.append(f"outputs/{job_id}_audio.wav")
            except Exception as e:
                logger.warning("Upload WAV to GCS for %s: %s", job_id, e)
        state_path = JOBS_STATE_DIR / f"{job_id}.json"
        if state_path.exists():
            try:
                from google.cloud import storage
                bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
                blob = bucket.blob(f"job_state/{job_id}.json")
                blob.upload_from_string(
                    state_path.read_text(encoding="utf-8"),
                    content_type="application/json",
                )
                uploaded_outputs.append(f"job_state/{job_id}.json")
            except Exception as e:
                logger.warning("Upload job_state to GCS for %s: %s", job_id, e)

    return {
        "uploaded_rag": uploaded_rag,
        "latest_rag": latest_rag,
        "uploaded_outputs": uploaded_outputs,
        "from_archive_outputs": from_archive_outputs,
        "jobs_synced": len(completed),
    }


@app.post("/api/restore-rag")
async def api_restore_rag(path: str = "rag_db/latest.zip"):
    """Restore RAG DB from a zip in the GCS output bucket (e.g. rag_db/latest.zip). Replaces local RAG_DIR contents."""
    if not GCS_OUTPUT_BUCKET:
        raise HTTPException(503, "GCS output bucket is not configured (GCS_OUTPUT_BUCKET)")
    path = (path or "rag_db/latest.zip").strip().lstrip("/")
    if not path.endswith(".zip"):
        raise HTTPException(400, "path must be a .zip object (e.g. rag_db/latest.zip)")
    ok = restore_rag_from_gcs(GCS_OUTPUT_BUCKET, path)
    if not ok:
        raise HTTPException(500, "Restore failed; check server logs")
    return {"ok": True, "restored_from": path}


@app.post("/api/merge-rag-from-bucket")
async def api_merge_rag_from_bucket(prefix: str = "job_state/"):
    """
    Re-index job_state JSON files from the GCS output bucket into the local RAG, then save merged RAG to bucket.
    """
    if not GCS_OUTPUT_BUCKET:
        raise HTTPException(503, "GCS output bucket is not configured (GCS_OUTPUT_BUCKET)")
    indexed, errors = _merge_rag_from_bucket()
    uploaded_rag, latest_rag = upload_rag_db_to_gcs(GCS_OUTPUT_BUCKET, prefix="rag_db")
    return {
        "ok": True,
        "indexed": indexed,
        "errors": errors if errors else None,
        "uploaded_rag": uploaded_rag,
        "latest_rag": latest_rag,
    }


@app.get("/api/audio/{job_id}")
async def get_audio(job_id: str):
    """Serve the preprocessed WAV for a job (available after Preprocess step). From local disk or GCS redirect."""
    state = get_job(job_id)
    if not state:
        raise HTTPException(404, "Job not found")
    wav_path = OUTPUT_DIR / f"{job_id}_audio.wav"
    if wav_path.exists():
        return FileResponse(wav_path, media_type="audio/wav")
    if GCS_OUTPUT_BUCKET:
        try:
            from google.cloud import storage
            import datetime
            client = _gcs_client_for_signing()
            bucket = client.bucket(GCS_OUTPUT_BUCKET)
            blob = bucket.blob(f"outputs/{job_id}_audio.wav")
            if blob.exists():
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(minutes=15),
                    method="GET",
                )
                return RedirectResponse(url=url, status_code=302)
        except Exception:
            pass
    raise HTTPException(404, "Audio not ready yet")


# ----- Folders -----

@app.get("/api/folders")
async def api_list_folders():
    """List all folders for dropdown and management."""
    t0 = time.perf_counter()
    try:
        folders = list_folders()
    except Exception as e:
        logger.exception("GET /api/folders failed: %s", e)
        raise HTTPException(503, "Failed to load folders. Check Cloud Run logs for details.")
    elapsed = time.perf_counter() - t0
    logger.info("GET /api/folders: %d folders in %.3fs", len(folders), elapsed)
    if elapsed > 0.2:
        logger.warning("GET /api/folders was slow (%.3fs) — check DB or disk", elapsed)
    return {"folders": folders}


@app.post("/api/folders")
async def api_create_folder(name: str = Form(...)):
    """Create a new folder."""
    try:
        folder = create_folder(name)
        return folder
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/folders/{folder_id:int}")
async def api_update_folder(folder_id: int, body: dict = Body(...)):
    """Rename a folder. Body: { \"name\": \"new name\" }."""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    try:
        folder = update_folder(folder_id, name)
        if folder is None:
            raise HTTPException(404, "Folder not found")
        return folder
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/folders/{folder_id:int}")
async def api_delete_folder(folder_id: int):
    """Delete a folder. Jobs in it are unassigned (folder_id set to null)."""
    if not delete_folder(folder_id):
        raise HTTPException(404, "Folder not found")
    return {"ok": True}


# ----- RAG search -----

def _parse_folder_ids(folder_ids: str | None) -> list[int] | None:
    """Parse comma-separated folder IDs from query string."""
    if not folder_ids or not folder_ids.strip():
        return None
    out = []
    for s in folder_ids.strip().split(","):
        s = s.strip()
        if not s:
            continue
        try:
            out.append(int(s))
        except ValueError:
            continue
    return out if out else None


@app.get("/api/search/transcripts")
async def api_search_transcripts(
    q: str = "",
    limit: int = RAG_SEARCH_LIMIT,
    folder_ids: str | None = None,
):
    """Search transcript segments; optional folder_ids (comma-separated) to filter by folders."""
    if not q or not q.strip():
        return {"results": []}
    fids = _parse_folder_ids(folder_ids)
    results = search_transcript_segments(q.strip(), limit=limit, folder_ids=fids)
    return {"results": results}


@app.get("/api/search/meetings")
async def api_search_meetings(
    q: str = "",
    limit: int = RAG_SEARCH_LIMIT,
    folder_ids: str | None = None,
):
    """Search meetings by main topic; optional folder_ids (comma-separated) to filter by folders."""
    if not q or not q.strip():
        return {"results": []}
    fids = _parse_folder_ids(folder_ids)
    results = search_meetings(q.strip(), limit=limit, folder_ids=fids)
    return {"results": results}


@app.get("/search/transcripts", response_class=HTMLResponse)
async def page_search_transcripts():
    """Transcript search page: search segments, click timestamp to play audio."""
    html_path = BASE_DIR / "templates" / "search-transcripts.html"
    if not html_path.exists():
        raise HTTPException(404, "search-transcripts.html not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/search/meetings", response_class=HTMLResponse)
async def page_search_meetings():
    """Meeting search page: search by topic, click meeting to see full processing results."""
    html_path = BASE_DIR / "templates" / "search-meetings.html"
    if not html_path.exists():
        raise HTTPException(404, "search-meetings.html not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    from server.config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
