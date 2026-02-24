"""SQLite database: folders and job–folder association for organizing uploads and filtering search."""
import logging
import sqlite3
import threading
import time
from pathlib import Path

# Project root for config
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_PATH

logger = logging.getLogger("audio_pipeline.db")

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    with _lock:
        conn = _get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                    original_filename TEXT,
                    file_hash TEXT,
                    status TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_folder_id ON jobs(folder_id);
            """)
            conn.commit()
        finally:
            conn.close()


def list_folders() -> list[dict]:
    """Return all folders ordered by name."""
    t0 = time.perf_counter()
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "SELECT id, name, created_at FROM folders ORDER BY name"
            )
            out = [{"id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in cur.fetchall()]
        finally:
            conn.close()
    elapsed = time.perf_counter() - t0
    logger.info("list_folders: %d folders in %.3fs", len(out), elapsed)
    return out


def create_folder(name: str) -> dict:
    """Create a folder. Returns the new folder dict with id."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Folder name is required")
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute("INSERT INTO folders (name) VALUES (?)", (name,))
            conn.commit()
            fid = cur.lastrowid
            row = conn.execute("SELECT id, name, created_at FROM folders WHERE id = ?", (fid,)).fetchone()
            return {"id": row["id"], "name": row["name"], "created_at": row["created_at"]}
        finally:
            conn.close()


def update_folder(folder_id: int, name: str) -> dict | None:
    """Rename a folder. Returns updated folder dict or None if not found."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Folder name is required")
    with _lock:
        conn = _get_conn()
        try:
            conn.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
            conn.commit()
            if conn.total_changes == 0:
                return None
            row = conn.execute("SELECT id, name, created_at FROM folders WHERE id = ?", (folder_id,)).fetchone()
            return {"id": row["id"], "name": row["name"], "created_at": row["created_at"]}
        finally:
            conn.close()


def delete_folder(folder_id: int) -> bool:
    """Delete a folder. Jobs in this folder get folder_id set to NULL. Returns True if folder existed."""
    with _lock:
        conn = _get_conn()
        try:
            if conn.execute("SELECT 1 FROM folders WHERE id = ?", (folder_id,)).fetchone() is None:
                return False
            conn.execute("UPDATE jobs SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
            conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
            conn.commit()
            return True
        finally:
            conn.close()


def upsert_job(job_id: str, folder_id: int | None, original_filename: str = "", file_hash: str | None = None, status: str = "pending") -> None:
    """Insert or replace job row (for pipeline completion / persistence)."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO jobs (job_id, folder_id, original_filename, file_hash, status)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     folder_id = excluded.folder_id,
                     original_filename = excluded.original_filename,
                     file_hash = excluded.file_hash,
                     status = excluded.status""",
                (job_id, folder_id, original_filename or "", file_hash or "", status),
            )
            conn.commit()
        finally:
            conn.close()


def get_job_folder_id(job_id: str) -> int | None:
    """Return folder_id for a job, or None."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT folder_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return row["folder_id"] if row and row["folder_id"] is not None else None
        finally:
            conn.close()


def delete_job(job_id: str) -> None:
    """Remove job row (when user removes job from list)."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()
