"""Web server: search over results in the output bucket. RAG sync runs in foreground with streaming progress."""
import asyncio
import json
import logging
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from config import BASE_DIR, GCS_OUTPUT_BUCKET, GCS_SIGNING_KEY_JSON, RAG_SEARCH_LIMIT
from app.folders import list_folders
from app.rag import search_transcript_segments, search_meetings
from app.sync import ensure_rag_synced_with_bucket

logger = logging.getLogger("web_server")

_app = None
_sync_last_result = None


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

    # ----- Sync (foreground with streaming progress) -----
    @_app.post("/api/sync")
    async def api_sync():
        """Run RAG sync in foreground and stream progress as Server-Sent Events."""

        async def event_stream():
            global _sync_last_result
            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            result_holder = []

            def progress_cb(msg):
                loop.call_soon_threadsafe(queue.put_nowait, ("progress", msg))

            def run_sync():
                try:
                    r = ensure_rag_synced_with_bucket(progress_callback=progress_cb)
                    result_holder.append(("ok", r))
                except Exception as e:
                    logger.exception("Sync failed: %s", e)
                    result_holder.append(("error", str(e)))
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

            sync_task = asyncio.create_task(asyncio.to_thread(run_sync))
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Still running…'})}\n\n"
                    continue
                if event[0] == "done":
                    break
                yield f"data: {json.dumps({'type': 'progress', 'message': event[1]})}\n\n"

            await sync_task
            if result_holder and result_holder[0][0] == "ok":
                restored, newly_indexed, errors = result_holder[0][1]
                _sync_last_result = {
                    "ok": True,
                    "restored": restored,
                    "newly_indexed": newly_indexed,
                    "errors": (errors[:20] if errors else None),
                }
                yield f"data: {json.dumps({'type': 'result', 'ok': True, 'restored': restored, 'newly_indexed': newly_indexed, 'errors': errors[:20] if errors else None})}\n\n"
            else:
                err_msg = result_holder[0][1] if result_holder else "Unknown error"
                _sync_last_result = {"ok": False, "error": err_msg}
                yield f"data: {json.dumps({'type': 'result', 'ok': False, 'error': err_msg})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @_app.get("/api/sync/status")
    async def api_sync_status():
        """Return result of the last completed sync, if any."""
        if _sync_last_result is None:
            return {"status": "never_run"}
        return {"status": "complete", "result": _sync_last_result}

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
