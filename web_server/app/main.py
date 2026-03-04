"""Web server: search over results in the output bucket. Syncs RAG from job_state on startup."""
import logging
import time
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from config import BASE_DIR, GCS_OUTPUT_BUCKET, GCS_SIGNING_KEY_JSON, RAG_SEARCH_LIMIT
from app.folders import list_folders
from app.rag import search_transcript_segments, search_meetings
from app.sync import ensure_rag_synced_with_bucket

logger = logging.getLogger("web_server")

# Lazy FastAPI app so we can run sync before routes are used
_app = None


def _gcs_client_for_signing():
    if not GCS_SIGNING_KEY_JSON:
        from google.cloud import storage
        return storage.Client()
    import json
    from google.cloud import storage
    from google.oauth2 import service_account
    info = json.loads(GCS_SIGNING_KEY_JSON)
    creds = service_account.Credentials.from_service_account_info(info)
    return storage.Client(credentials=creds, project=info.get("project_id"))


def _run_startup():
    """Restore RAG from bucket, merge new jobs, optionally upload updated RAG."""
    restored, newly_indexed, errors = ensure_rag_synced_with_bucket()
    logger.info("Startup: RAG restored=%s, newly_indexed=%d, errors=%d", restored, newly_indexed, len(errors))


def create_app():
    global _app
    if _app is not None:
        return _app
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    _app = FastAPI(title="Search – Audio Results", description="Search transcript and meeting results from the output bucket")
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @_app.on_event("startup")
    def startup():
        import threading
        t = threading.Thread(target=_run_startup, daemon=True)
        t.start()
        logger.info("Startup: server binding; RAG sync running in background.")

    # ----- Config & folders -----
    @_app.get("/api/config")
    async def api_config():
        return {"gcs_output_bucket": bool(GCS_OUTPUT_BUCKET)}

    @_app.get("/api/folders")
    async def api_list_folders():
        folders = list_folders()
        return {"folders": folders}

    # ----- Search API -----
    def _parse_folder_ids(folder_ids: str | None) -> list[int] | None:
        if not folder_ids or not folder_ids.strip():
            return None
        out = []
        for s in folder_ids.strip().split(","):
            try:
                out.append(int(s.strip()))
            except ValueError:
                continue
        return out if out else None

    @_app.get("/api/search/transcripts")
    async def api_search_transcripts(
        q: str = "",
        limit: int = RAG_SEARCH_LIMIT,
        folder_ids: str | None = None,
    ):
        if not q or not q.strip():
            return {"results": []}
        fids = _parse_folder_ids(folder_ids)
        results = search_transcript_segments(q.strip(), limit=limit, folder_ids=fids)
        return {"results": results}

    @_app.get("/api/search/meetings")
    async def api_search_meetings(
        q: str = "",
        limit: int = RAG_SEARCH_LIMIT,
        folder_ids: str | None = None,
    ):
        if not q or not q.strip():
            return {"results": []}
        fids = _parse_folder_ids(folder_ids)
        results = search_meetings(q.strip(), limit=limit, folder_ids=fids)
        return {"results": results}

    # ----- Result & audio from bucket -----
    @_app.get("/api/result/{job_id}")
    async def api_result(job_id: str):
        """Get full result for a job from output bucket job_state/."""
        if not GCS_OUTPUT_BUCKET:
            raise HTTPException(503, "Output bucket not configured")
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_OUTPUT_BUCKET)
        blob = bucket.blob(f"job_state/{job_id}.json")
        if not blob.exists():
            raise HTTPException(404, "Job not found")
        import json
        data = json.loads(blob.download_as_string().decode("utf-8"))
        return {"job_id": job_id, "status": data.get("status"), "result": data.get("result")}

    @_app.get("/api/audio/{job_id}")
    async def api_audio(job_id: str):
        """Redirect to signed URL for WAV in output bucket, or 404."""
        if not GCS_OUTPUT_BUCKET:
            raise HTTPException(503, "Output bucket not configured")
        import datetime
        bucket = _gcs_client_for_signing().bucket(GCS_OUTPUT_BUCKET)
        blob = bucket.blob(f"outputs/{job_id}_audio.wav")
        if not blob.exists():
            raise HTTPException(404, "Audio not found")
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
        )
        return RedirectResponse(url=url, status_code=302)

    # ----- Sync trigger -----
    @_app.post("/api/sync")
    async def api_sync():
        """Re-run RAG sync: merge new jobs from bucket and optionally upload RAG."""
        restored, newly_indexed, errors = ensure_rag_synced_with_bucket()
        return {"ok": True, "restored": restored, "newly_indexed": newly_indexed, "errors": errors[:20] if errors else None}

    # ----- Search pages -----
    @_app.get("/", response_class=HTMLResponse)
    async def index():
        """Landing: redirect to search transcripts or serve simple search hub."""
        html_path = BASE_DIR / "templates" / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<html><body><h1>Search</h1><a href='/search/transcripts'>Search transcripts</a> | <a href='/search/meetings'>Search meetings</a></body></html>")

    @_app.get("/search/transcripts", response_class=HTMLResponse)
    async def page_search_transcripts():
        path = BASE_DIR / "templates" / "search-transcripts.html"
        if not path.exists():
            raise HTTPException(404, "search-transcripts.html not found")
        return HTMLResponse(content=path.read_text(encoding="utf-8"))

    @_app.get("/search/meetings", response_class=HTMLResponse)
    async def page_search_meetings():
        path = BASE_DIR / "templates" / "search-meetings.html"
        if not path.exists():
            raise HTTPException(404, "search-meetings.html not found")
        return HTMLResponse(content=path.read_text(encoding="utf-8"))

    return _app


app = create_app()
