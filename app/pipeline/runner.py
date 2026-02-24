"""Pipeline runner with step status tracking and queue."""
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from config import OUTPUT_DIR

logger = logging.getLogger("audio_pipeline.runner")

from .steps import PipelineContext, preprocess, transcribe, analyze_llm

JOBS_STATE_DIR = OUTPUT_DIR / "job_state"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepState:
    name: str
    status: StepStatus = StepStatus.PENDING
    message: str = ""
    detail: str = ""
    progress: float = 0.0  # 0.0 to 100.0
    eta_seconds: float | None = None  # Estimated time remaining in seconds
    start_time: float | None = None  # When step started (for ETA calculation)


@dataclass
class PipelineState:
    job_id: str
    original_filename: str = ""
    status: str = "pending"  # pending | running | completed | failed | cancelled
    steps: dict[str, StepState] = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    error: str | None = None
    cancelled: bool = False
    file_hash: str | None = None  # for already-processed tracking
    folder_id: int | None = None  # for organizing into folders

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "original_filename": self.original_filename,
            "status": self.status,
            "steps": {
                k: {
                    "name": v.name,
                    "status": v.status.value,
                    "message": v.message,
                    "detail": v.detail,
                    "progress": v.progress,
                    "eta_seconds": v.eta_seconds,
                }
                for k, v in self.steps.items()
            },
            "result": self.result,
            "error": self.error,
            "folder_id": self.folder_id,
        }

    def to_persist_dict(self) -> dict[str, Any]:
        """Full dict for persistence (includes file_hash, folder_id)."""
        d = self.to_dict()
        d["file_hash"] = self.file_hash
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineState":
        """Reconstruct state from persisted dict."""
        steps_dict = d.get("steps") or {}
        steps = {}
        for k, v in steps_dict.items():
            if isinstance(v, dict):
                status_val = v.get("status", "pending")
                try:
                    step_status = StepStatus(status_val)
                except ValueError:
                    step_status = StepStatus.PENDING
                steps[k] = StepState(
                    name=v.get("name", k),
                    status=step_status,
                    message=v.get("message", ""),
                    detail=v.get("detail", ""),
                    progress=v.get("progress", 0.0),
                    eta_seconds=v.get("eta_seconds"),
                    start_time=v.get("start_time"),
                )
        fid = d.get("folder_id")
        if fid is not None:
            try:
                fid = int(fid)
            except (TypeError, ValueError):
                fid = None
        return cls(
            job_id=d.get("job_id", ""),
            original_filename=d.get("original_filename", ""),
            status=d.get("status", "pending"),
            steps=steps,
            result=d.get("result") or {},
            error=d.get("error"),
            file_hash=d.get("file_hash"),
            folder_id=fid,
        )


# In-memory job store (persisted to disk for completed/failed jobs)
_jobs: dict[str, PipelineState] = {}
_lock = threading.Lock()

# Queue: pending items to process. Each item: {queue_id, upload_path, original_filename, file_hash, folder_id, status}
_queue: list[dict] = []
# File hashes that have completed successfully (for "already processed" warning)
_processed_hashes: set[str] = set()
# job_id -> file_hash for removing from _processed_hashes when job is deleted
_job_to_hash: dict[str, str] = {}
# Paused: worker will not start next job
_queue_paused: bool = False
# Currently running job_id (from queue worker)
_current_job_id: str | None = None
# One-time: persisted jobs loaded in worker so startup is fast
_persisted_loaded: bool = False


def _save_job_state(state: PipelineState) -> None:
    """Persist completed, failed, or cancelled job to disk and to SQL DB so it survives restarts."""
    if state.status not in ("completed", "failed", "cancelled"):
        return
    JOBS_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = JOBS_STATE_DIR / f"{state.job_id}.json"
    try:
        path.write_text(json.dumps(state.to_persist_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        from app.db import upsert_job
        upsert_job(
            state.job_id,
            folder_id=state.folder_id,
            original_filename=state.original_filename,
            file_hash=state.file_hash,
            status=state.status,
        )
    except Exception:
        pass


def _load_persisted_jobs() -> None:
    """Load previously persisted jobs from disk. Parse files outside the lock so /api/queue does not block."""
    if not JOBS_STATE_DIR.exists():
        logger.info("Load persisted jobs: no job_state dir, skipping")
        return
    paths = list(JOBS_STATE_DIR.glob("*.json"))
    if not paths:
        logger.info("Load persisted jobs: 0 files, skipping")
        return
    t0 = time.perf_counter()
    logger.info("Load persisted jobs: reading %d JSON files (outside lock)...", len(paths))
    loaded: list[tuple[PipelineState, str | None]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state = PipelineState.from_dict(data)
            h = state.file_hash if state.status == "completed" else None
            loaded.append((state, h))
        except Exception as e:
            logger.debug("Load persisted jobs: skip %s: %s", path.name, e)
    t_read = time.perf_counter() - t0
    logger.info("Load persisted jobs: parsed %d jobs in %.3fs, applying under lock...", len(loaded), t_read)
    t1 = time.perf_counter()
    with _lock:
        for state, h in loaded:
            _jobs[state.job_id] = state
            if h:
                _processed_hashes.add(h)
                _job_to_hash[state.job_id] = h
    logger.info("Load persisted jobs: done. %d jobs in memory in %.3fs total (lock held %.3fs)", len(loaded), time.perf_counter() - t0, time.perf_counter() - t1)


def get_job(job_id: str) -> PipelineState | None:
    return _jobs.get(job_id)


def is_duplicate_in_queue(file_hash: str) -> bool:
    """True if this file_hash is already in the queue (pending or running)."""
    with _lock:
        if _current_job_id:
            s = _jobs.get(_current_job_id)
            if s and s.file_hash == file_hash:
                return True
        for item in _queue:
            if item.get("file_hash") == file_hash:
                return True
    return False


def is_already_processed(file_hash: str) -> bool:
    """True if this file was previously completed successfully."""
    with _lock:
        return file_hash in _processed_hashes


def get_queue_state() -> dict:
    """Return queue state: paused, current_job_id, pending list, all jobs."""
    t0 = time.perf_counter()
    with _lock:
        wait_ms = (time.perf_counter() - t0) * 1000
        if wait_ms > 50:
            logger.warning("get_queue_state: waited %.0fms for lock (worker may be loading persisted jobs)", wait_ms)
        pending = [
            {
                "queue_id": item["queue_id"],
                "original_filename": item["original_filename"],
                "file_hash": item.get("file_hash"),
                "folder_id": item.get("folder_id"),
                "status": item["status"],
            }
            for item in _queue
        ]
        jobs = [s.to_dict() for s in _jobs.values()]
    elapsed = (time.perf_counter() - t0) * 1000
    if elapsed > 100:
        logger.info("get_queue_state: %d jobs, %.0fms (lock wait + build)", len(jobs), elapsed)
    return {
        "paused": _queue_paused,
        "current_job_id": _current_job_id,
        "pending": pending,
        "jobs": jobs,
    }


def add_to_queue(upload_path: Path, original_filename: str, file_hash: str, folder_id: int | None = None) -> str:
    """Add a file to the queue. Returns queue_id.
    Only appends to the queue; never interrupts or replaces the current job.
    The worker processes one job at a time and picks the next item only after the current run finishes.
    """
    queue_id = str(uuid.uuid4())
    with _lock:
        _queue.append({
            "queue_id": queue_id,
            "upload_path": upload_path,
            "original_filename": original_filename,
            "file_hash": file_hash,
            "folder_id": folder_id,
            "status": "pending",
        })
    return queue_id


def remove_from_queue(queue_id: str) -> bool:
    """Remove a pending item by queue_id. Returns True if removed."""
    with _lock:
        for i, item in enumerate(_queue):
            if item["queue_id"] == queue_id and item["status"] == "pending":
                _queue.pop(i)
                return True
    return False


def remove_job(job_id: str) -> bool:
    """Remove a job from _jobs and DB. If completed, also remove its hash from _processed_hashes. Returns True if removed."""
    with _lock:
        state = _jobs.get(job_id)
        if not state:
            return False
        del _jobs[job_id]
        h = _job_to_hash.pop(job_id, None)
        if h:
            _processed_hashes.discard(h)
        persist_path = JOBS_STATE_DIR / f"{job_id}.json"
        if persist_path.exists():
            try:
                persist_path.unlink()
            except Exception:
                pass
        try:
            from app.db import delete_job
            delete_job(job_id)
        except Exception:
            pass
        return True


def cancel_job(job_id: str) -> bool:
    """Request cancellation of a running job. Pipeline will stop between steps or during long-running steps."""
    with _lock:
        state = _jobs.get(job_id)
        if not state:
            # Allow cancel by current job id in case of race
            if _current_job_id and _current_job_id == job_id:
                state = _jobs.get(_current_job_id)
        if not state or state.status != "running":
            return False
        state.cancelled = True
        return True


def pause_queue() -> None:
    with _lock:
        global _queue_paused
        _queue_paused = True


def resume_queue() -> None:
    with _lock:
        global _queue_paused
        _queue_paused = False


def _worker_loop() -> None:
    """Background worker: process queue one job at a time when not paused.
    New uploads (from any client) are appended to _queue and do not affect the running job.
    The current job always runs to completion (or fail/cancel) before the next is started.
    """
    global _current_job_id, _persisted_loaded
    if not _persisted_loaded:
        _load_persisted_jobs()
        _persisted_loaded = True
    import time
    while True:
        have_work = False
        upload_path = original_filename = file_hash = folder_id = job_id = None
        with _lock:
            if _queue_paused or not _queue:
                _current_job_id = None
            else:
                for i, q in enumerate(_queue):
                    if q["status"] == "pending":
                        q["status"] = "running"
                        upload_path = q["upload_path"]
                        original_filename = q["original_filename"]
                        file_hash = q.get("file_hash") or ""
                        folder_id = q.get("folder_id")
                        job_id = str(uuid.uuid4())
                        q["job_id"] = job_id
                        have_work = True
                        break
                else:
                    _current_job_id = None
        if not have_work:
            time.sleep(1)
            continue

        # Pre-create job state (lock released so GET /api/queue is not blocked)
        state = PipelineState(
            job_id=job_id,
            original_filename=original_filename,
            file_hash=file_hash or None,
            folder_id=folder_id,
        )
        state.steps = {
            "preprocess": StepState("Preprocess audio"),
            "transcribe": StepState("Transcribe (Whisper)"),
            "analyze": StepState("Extract topics & truth statements"),
        }
        state.status = "running"
        with _lock:
            _jobs[job_id] = state
            _current_job_id = job_id

        try:
            run_pipeline(upload_path, original_filename, job_id=job_id, file_hash=file_hash or None, folder_id=folder_id)
        except Exception:
            pass  # state already set to failed in run_pipeline
        finally:
            with _lock:
                _current_job_id = None
                if state.status == "completed" and state.file_hash:
                    _processed_hashes.add(state.file_hash)
                    _job_to_hash[job_id] = state.file_hash
                if state.status in ("completed", "failed", "cancelled"):
                    _save_job_state(state)
                # Remove this item from queue
                for i, q in enumerate(_queue):
                    if q.get("job_id") == job_id:
                        _queue.pop(i)
                        break


def start_queue_worker() -> None:
    """Start the background queue worker thread (call once at app startup). Persisted jobs load inside the worker so startup stays fast."""
    t = threading.Thread(target=_worker_loop, daemon=True)
    t.start()


def run_pipeline(
    upload_path: Path,
    original_filename: str,
    job_id: str | None = None,
    file_hash: str | None = None,
    folder_id: int | None = None,
) -> str:
    """Run the full pipeline; update shared state for status. Returns job_id. Checks cancelled between steps."""
    job_id = job_id or str(uuid.uuid4())
    ctx = PipelineContext(job_id=job_id, upload_path=upload_path, original_filename=original_filename)

    state = _jobs.get(job_id)
    if not state:
        state = PipelineState(
            job_id=job_id,
            original_filename=original_filename,
            file_hash=file_hash,
            folder_id=folder_id,
        )
        state.steps = {
            "preprocess": StepState("Preprocess audio"),
            "transcribe": StepState("Transcribe (Whisper)"),
            "analyze": StepState("Extract topics & truth statements"),
        }
        _jobs[job_id] = state
    state.status = "running"
    state.cancelled = False
    if file_hash:
        state.file_hash = file_hash
    if folder_id is not None:
        state.folder_id = folder_id

    def is_cancelled() -> bool:
        with _lock:
            return _jobs.get(job_id, state).cancelled

    def set_step_running(step_id: str, message: str = "", progress: float = 0.0, eta_seconds: float | None = None):
        step = state.steps[step_id]
        step.status = StepStatus.RUNNING
        step.message = message
        step.progress = max(0.0, min(100.0, progress))
        step.eta_seconds = eta_seconds
        if step.start_time is None:
            step.start_time = time.perf_counter()

    def set_step_ok(step_id: str, detail: str = ""):
        step = state.steps[step_id]
        step.status = StepStatus.COMPLETED
        step.message = "Done"
        step.detail = detail
        step.progress = 100.0
        step.eta_seconds = None

    def set_step_fail(step_id: str, err: str):
        step = state.steps[step_id]
        step.status = StepStatus.FAILED
        step.message = "Failed"
        step.detail = str(err)
        step.progress = 0.0
        step.eta_seconds = None

    try:
        if is_cancelled():
            state.status = "cancelled"
            state.error = "Cancelled by user"
            return job_id
        
        # Preprocess step
        set_step_running("preprocess", "Starting...", 0.0, None)
        preprocess_start = time.perf_counter()
        def preprocess_progress(msg: str, progress: float = 0.0):
            elapsed = time.perf_counter() - preprocess_start
            eta = None
            if progress > 0 and progress < 100:
                eta = (elapsed / progress) * (100 - progress)
            set_step_running("preprocess", msg, progress, eta)
        preprocess(ctx, on_progress=preprocess_progress)
        if is_cancelled():
            state.status = "cancelled"
            state.error = "Cancelled by user"
            return job_id
        set_step_ok("preprocess", "Converted to WAV and normalized")
        state.result["audio_ready"] = True

        if is_cancelled():
            state.status = "cancelled"
            state.error = "Cancelled by user"
            return job_id
        
        # Transcribe step
        set_step_running("transcribe", "Starting...", 0.0, None)
        transcribe_start = time.perf_counter()
        def transcribe_progress(msg: str, progress: float = 0.0):
            elapsed = time.perf_counter() - transcribe_start
            eta = None
            if progress > 0 and progress < 100:
                eta = (elapsed / progress) * (100 - progress)
            set_step_running("transcribe", msg, progress, eta)
        transcribe(ctx, on_progress=transcribe_progress, is_cancelled=is_cancelled)
        if is_cancelled():
            state.status = "cancelled"
            state.error = "Cancelled by user"
            return job_id
        set_step_ok("transcribe", f"{len(ctx.timestamps)} segments")
        state.result["transcription"] = ctx.transcription
        state.result["timestamps"] = ctx.timestamps

        if is_cancelled():
            state.status = "cancelled"
            state.error = "Cancelled by user"
            return job_id
        
        # Analyze step
        set_step_running("analyze", "Starting...", 0.0, None)
        analyze_start = time.perf_counter()
        def analyze_progress(msg: str, progress: float = 0.0):
            elapsed = time.perf_counter() - analyze_start
            eta = None
            if progress > 0 and progress < 100:
                eta = (elapsed / progress) * (100 - progress)
            set_step_running("analyze", msg, progress, eta)
        analyze_llm(ctx, on_progress=analyze_progress, is_cancelled=is_cancelled)
        if is_cancelled():
            state.status = "cancelled"
            state.error = "Cancelled by user"
            return job_id
        set_step_ok("analyze", "Main topic, subtopics, and truth statements extracted")
        state.result["main_topic"] = ctx.main_topic
        state.result["subtopics"] = ctx.subtopics
        state.result["truth_statements_md"] = ctx.truth_statements_md
        state.result["original_filename"] = ctx.original_filename

        state.status = "completed"

        try:
            from app.rag import index_transcript_segments, index_meeting
            index_transcript_segments(
                job_id=ctx.job_id,
                timestamps=ctx.timestamps,
                original_filename=ctx.original_filename,
                folder_id=state.folder_id,
            )
            index_meeting(
                job_id=ctx.job_id,
                original_filename=ctx.original_filename,
                main_topic=ctx.main_topic,
                subtopics=ctx.subtopics,
                folder_id=state.folder_id,
            )
        except Exception:
            pass
    except Exception as e:
        state.status = "failed"
        state.error = str(e)
        for sid, s in state.steps.items():
            if s.status == StepStatus.RUNNING:
                set_step_fail(sid, str(e))
                break
        raise
    return job_id
