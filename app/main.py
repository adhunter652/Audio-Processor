"""FastAPI app: upload, status, results, folders, and search."""
import hashlib
import logging
import time
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import (
    ALLOWED_EXTENSIONS,
    BASE_DIR,
    GCS_OUTPUT_BUCKET,
    GCS_UPLOAD_BUCKET,
    MAX_FILE_SIZE_BYTES,
    OUTPUT_DIR,
    RAG_SEARCH_LIMIT,
    UPLOAD_DIR,
)
from app.db import init_db, list_folders, create_folder, update_folder, delete_folder
from app.pipeline.runner import (
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
from app.pipeline.steps import check_ffmpeg_available
from app.rag import search_transcript_segments, search_meetings

logger = logging.getLogger("audio_pipeline")
app = FastAPI(title="Audio Processing Pipeline", description="Upload audio → transcribe → topics & truth statements")


def _ensure_pipeline_logging():
    """Ensure audio_pipeline loggers emit INFO to the console (for timing diagnostics)."""
    log = logging.getLogger("audio_pipeline")
    log.setLevel(logging.INFO)
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        log.addHandler(h)


def _run_startup_tasks():
    """Run DB init, ffmpeg check, and queue worker in a background thread so the server can bind to PORT immediately (required for Cloud Run)."""
    _ensure_pipeline_logging()
    t0 = time.perf_counter()
    logger.info("Startup (background): initializing database...")
    init_db()
    logger.info("Startup (background): init_db took %.3fs", time.perf_counter() - t0)
    t1 = time.perf_counter()
    ok, msg = check_ffmpeg_available()
    if not ok:
        logging.getLogger("uvicorn.error").warning(
            "FFmpeg not available: %s Pipeline will fail for .mp3/.mp4 uploads. WAV may still work.", msg
        )
    logger.info("Startup (background): check_ffmpeg took %.3fs", time.perf_counter() - t1)
    t2 = time.perf_counter()
    logger.info("Startup (background): starting queue worker (persisted jobs will load in worker thread)...")
    start_queue_worker()
    logger.info("Startup (background): start_queue_worker took %.3fs (worker runs in background)", time.perf_counter() - t2)
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
    """Return client config (e.g. whether to use direct GCS upload)."""
    return {"gcs_upload": bool(GCS_UPLOAD_BUCKET)}


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
        client = storage.Client()
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
            client = storage.Client()
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
    folders = list_folders()
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
    from config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
