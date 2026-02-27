"""Database: folders and job–folder association. Supports SQLite (local), Cloud SQL (PostgreSQL), and GCS (storage bucket)."""
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

# Project root for config
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    DATABASE_PATH,
    USE_CLOUD_SQL,
    USE_GCS_METADATA,
    GCS_OUTPUT_BUCKET,
    CLOUD_SQL_CONNECTION_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
)

logger = logging.getLogger("audio_pipeline.db")

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()

# GCS metadata paths (when USE_GCS_METADATA)
_GCS_FOLDERS_KEY = "metadata/folders.json"
_GCS_JOBS_PREFIX = "metadata/jobs/"
_GCS_JOB_STATE_PREFIX = "job_state/"

# Cloud SQL connector (lazy init)
_cloud_sql_connector = None


def _get_cloud_sql_conn():
    """Return a connection to Cloud SQL (PostgreSQL) using the Python Connector."""
    global _cloud_sql_connector
    if _cloud_sql_connector is None:
        from google.cloud.sql.connector import Connector
        _cloud_sql_connector = Connector()
    return _cloud_sql_connector.connect(
        CLOUD_SQL_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
    )


def _row_to_dict(cursor, row: tuple) -> dict:
    """Convert a pg8000 tuple row to a dict keyed by column name."""
    if row is None:
        return None
    names = [d[0] for d in cursor.description] if cursor.description else []
    return dict(zip(names, row))


def _get_conn():
    """Return a database connection (SQLite or Cloud SQL). Caller must close it."""
    if USE_CLOUD_SQL:
        return _get_cloud_sql_conn()
    import sqlite3
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_one(cursor, conn) -> dict | None:
    """Fetch one row and return as dict (SQLite Row or pg8000 tuple converted)."""
    row = cursor.fetchone()
    if row is None:
        return None
    if USE_CLOUD_SQL:
        return _row_to_dict(cursor, row)
    return dict(row)


def _fetch_all(cursor, conn) -> list[dict]:
    """Fetch all rows and return as list of dicts."""
    rows = cursor.fetchall()
    if USE_CLOUD_SQL:
        return [_row_to_dict(cursor, r) for r in rows]
    return [dict(r) for r in rows]


def _param_placeholder(pos: int) -> str:
    """Return the placeholder for the given parameter index (for building queries)."""
    return "?" if not USE_CLOUD_SQL else "%s"


# ----- GCS metadata backend (when USE_GCS_METADATA) -----

def _gcs_bucket():
    """Return the GCS bucket used for metadata. Call only when USE_GCS_METADATA."""
    from google.cloud import storage
    return storage.Client().bucket(GCS_OUTPUT_BUCKET)


def _gcs_read_json(key: str) -> dict | list | None:
    """Read a GCS object as JSON. Returns None if the object does not exist."""
    blob = _gcs_bucket().blob(key)
    try:
        data = blob.download_as_string()
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _gcs_write_json(key: str, data: dict | list) -> None:
    """Write JSON to a GCS object."""
    blob = _gcs_bucket().blob(key)
    blob.upload_from_string(
        json.dumps(data, indent=2),
        content_type="application/json",
    )


def _gcs_list_blobs(prefix: str) -> list:
    """List blob names with the given prefix."""
    bucket = _gcs_bucket()
    return [b.name for b in bucket.list_blobs(prefix=prefix)]


def _gcs_delete(key: str) -> None:
    """Delete a GCS object if it exists."""
    blob = _gcs_bucket().blob(key)
    try:
        blob.delete()
    except Exception:
        pass


def init_db() -> None:
    """Create tables if they do not exist (SQL); or ensure GCS metadata layout exists."""
    if USE_GCS_METADATA:
        with _lock:
            data = _gcs_read_json(_GCS_FOLDERS_KEY)
            if data is None:
                _gcs_write_json(_GCS_FOLDERS_KEY, {"next_id": 1, "folders": []})
                logger.info("init_db: created metadata/folders.json in gs://%s", GCS_OUTPUT_BUCKET)
        return
    with _lock:
        conn = _get_conn()
        try:
            if USE_CLOUD_SQL:
                cur = conn.cursor()
                try:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS folders (
                            id SERIAL PRIMARY KEY,
                            name TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS jobs (
                            job_id TEXT PRIMARY KEY,
                            folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                            original_filename TEXT,
                            file_hash TEXT,
                            status TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_jobs_folder_id ON jobs(folder_id);
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS job_state (
                            job_id TEXT PRIMARY KEY,
                            state_json JSONB NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                finally:
                    cur.close()
                conn.commit()
            else:
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
    if USE_GCS_METADATA:
        with _lock:
            data = _gcs_read_json(_GCS_FOLDERS_KEY)
            out = (data.get("folders") or []) if isinstance(data, dict) else []
        out = sorted(out, key=lambda r: (r.get("name") or "").lower())
        elapsed = time.perf_counter() - t0
        logger.info("list_folders: %d folders in %.3fs", len(out), elapsed)
        return out
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, created_at FROM folders ORDER BY name")
            out = _fetch_all(cur, conn)
            # Normalize created_at to string for JSON if needed (Postgres may return datetime)
            for r in out:
                if hasattr(r.get("created_at"), "isoformat"):
                    r["created_at"] = r["created_at"].isoformat()
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
    if USE_GCS_METADATA:
        with _lock:
            data = _gcs_read_json(_GCS_FOLDERS_KEY)
            if not isinstance(data, dict):
                data = {"next_id": 1, "folders": []}
            folders = data.get("folders") or []
            fid = data.get("next_id", 1)
            created_at = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
            row = {"id": fid, "name": name, "created_at": created_at}
            folders.append(row)
            data["folders"] = folders
            data["next_id"] = fid + 1
            _gcs_write_json(_GCS_FOLDERS_KEY, data)
        return row
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            if USE_CLOUD_SQL:
                cur.execute("INSERT INTO folders (name) VALUES (%s) RETURNING id, name, created_at", (name,))
                row = _fetch_one(cur, conn)
                conn.commit()
            else:
                cur.execute("INSERT INTO folders (name) VALUES (?)", (name,))
                conn.commit()
                fid = cur.lastrowid
                cur.execute("SELECT id, name, created_at FROM folders WHERE id = ?", (fid,))
                row = _fetch_one(cur, conn)
            if row and hasattr(row.get("created_at"), "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
            return row
        finally:
            conn.close()


def update_folder(folder_id: int, name: str) -> dict | None:
    """Rename a folder. Returns updated folder dict or None if not found."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Folder name is required")
    if USE_GCS_METADATA:
        with _lock:
            data = _gcs_read_json(_GCS_FOLDERS_KEY)
            if not isinstance(data, dict):
                return None
            folders = data.get("folders") or []
            for f in folders:
                if f.get("id") == folder_id:
                    f["name"] = name
                    data["folders"] = folders
                    _gcs_write_json(_GCS_FOLDERS_KEY, data)
                    return f
            return None
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            if USE_CLOUD_SQL:
                cur.execute("UPDATE folders SET name = %s WHERE id = %s", (name, folder_id))
                conn.commit()
                if cur.rowcount == 0:
                    return None
                cur.execute("SELECT id, name, created_at FROM folders WHERE id = %s", (folder_id,))
            else:
                cur.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
                conn.commit()
                if conn.total_changes == 0:
                    return None
                cur.execute("SELECT id, name, created_at FROM folders WHERE id = ?", (folder_id,))
            row = _fetch_one(cur, conn)
            if row and hasattr(row.get("created_at"), "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
            return row
        finally:
            conn.close()


def delete_folder(folder_id: int) -> bool:
    """Delete a folder. Jobs in this folder get folder_id set to NULL. Returns True if folder existed."""
    if USE_GCS_METADATA:
        with _lock:
            data = _gcs_read_json(_GCS_FOLDERS_KEY)
            if not isinstance(data, dict):
                return False
            folders = data.get("folders") or []
            found = any(f.get("id") == folder_id for f in folders)
            if not found:
                return False
            # Clear folder_id on any job that had this folder
            bucket = _gcs_bucket()
            for key in _gcs_list_blobs(_GCS_JOBS_PREFIX):
                if not key.endswith(".json"):
                    continue
                blob = bucket.blob(key)
                try:
                    job_data = json.loads(blob.download_as_string().decode("utf-8"))
                    if job_data.get("folder_id") == folder_id:
                        job_data["folder_id"] = None
                        blob.upload_from_string(
                            json.dumps(job_data, indent=2),
                            content_type="application/json",
                        )
                except Exception:
                    pass
            data["folders"] = [f for f in folders if f.get("id") != folder_id]
            _gcs_write_json(_GCS_FOLDERS_KEY, data)
            return True
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            if USE_CLOUD_SQL:
                cur.execute("SELECT 1 FROM folders WHERE id = %s", (folder_id,))
                if cur.fetchone() is None:
                    return False
                cur.execute("UPDATE jobs SET folder_id = NULL WHERE folder_id = %s", (folder_id,))
                cur.execute("DELETE FROM folders WHERE id = %s", (folder_id,))
            else:
                cur.execute("SELECT 1 FROM folders WHERE id = ?", (folder_id,))
                if cur.fetchone() is None:
                    return False
                cur.execute("UPDATE jobs SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
                cur.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
            conn.commit()
            return True
        finally:
            conn.close()


def upsert_job(
    job_id: str,
    folder_id: int | None,
    original_filename: str = "",
    file_hash: str | None = None,
    status: str = "pending",
) -> None:
    """Insert or replace job row (for pipeline completion / persistence)."""
    if USE_GCS_METADATA:
        key = f"{_GCS_JOBS_PREFIX}{job_id}.json"
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        with _lock:
            existing = _gcs_read_json(key)
            if isinstance(existing, dict) and existing.get("created_at"):
                created_at = existing["created_at"]
            _gcs_write_json(key, {
                "folder_id": folder_id,
                "original_filename": original_filename or "",
                "file_hash": file_hash or "",
                "status": status,
                "created_at": created_at,
            })
        return
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            if USE_CLOUD_SQL:
                cur.execute(
                    """INSERT INTO jobs (job_id, folder_id, original_filename, file_hash, status)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT(job_id) DO UPDATE SET
                         folder_id = EXCLUDED.folder_id,
                         original_filename = EXCLUDED.original_filename,
                         file_hash = EXCLUDED.file_hash,
                         status = EXCLUDED.status""",
                    (job_id, folder_id, original_filename or "", file_hash or "", status),
                )
            else:
                cur.execute(
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
    if USE_GCS_METADATA:
        key = f"{_GCS_JOBS_PREFIX}{job_id}.json"
        data = _gcs_read_json(key)
        if isinstance(data, dict) and data.get("folder_id") is not None:
            return data["folder_id"]
        return None
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            if USE_CLOUD_SQL:
                cur.execute("SELECT folder_id FROM jobs WHERE job_id = %s", (job_id,))
            else:
                cur.execute("SELECT folder_id FROM jobs WHERE job_id = ?", (job_id,))
            row = _fetch_one(cur, conn)
            return row["folder_id"] if row and row.get("folder_id") is not None else None
        finally:
            conn.close()


def delete_job(job_id: str) -> None:
    """Remove job row (when user removes job from list)."""
    if USE_GCS_METADATA:
        with _lock:
            _gcs_delete(f"{_GCS_JOBS_PREFIX}{job_id}.json")
            _gcs_delete(f"{_GCS_JOB_STATE_PREFIX}{job_id}.json")
        return
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            if USE_CLOUD_SQL:
                cur.execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
                cur.execute("DELETE FROM job_state WHERE job_id = %s", (job_id,))
            else:
                cur.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()


# ----- Job state (Cloud SQL or GCS persistence of pipeline state JSON) -----

def save_job_state(job_id: str, state_json: dict) -> None:
    """Persist job state JSON (Cloud SQL or GCS). No-op when using SQLite only."""
    if USE_GCS_METADATA:
        with _lock:
            _gcs_write_json(f"{_GCS_JOB_STATE_PREFIX}{job_id}.json", state_json)
        return
    if not USE_CLOUD_SQL:
        return
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO job_state (job_id, state_json, updated_at)
                   VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
                   ON CONFLICT(job_id) DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = CURRENT_TIMESTAMP""",
                (job_id, json.dumps(state_json)),
            )
            conn.commit()
        finally:
            conn.close()


def load_all_job_states() -> list[tuple[str, dict]]:
    """Load all persisted job states (Cloud SQL or GCS). Returns list of (job_id, state_dict)."""
    if USE_GCS_METADATA:
        out = []
        bucket = _gcs_bucket()
        for key in _gcs_list_blobs(_GCS_JOB_STATE_PREFIX):
            if not key.endswith(".json"):
                continue
            job_id = key[len(_GCS_JOB_STATE_PREFIX):-5]  # strip prefix and .json
            try:
                data = _gcs_read_json(key)
                if isinstance(data, dict):
                    out.append((job_id, data))
            except Exception:
                pass
        return out
    if not USE_CLOUD_SQL:
        return []
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT job_id, state_json FROM job_state")
            rows = _fetch_all(cur, conn)
            out = []
            for r in rows:
                js = r.get("state_json")
                if js is None:
                    continue
                if isinstance(js, dict):
                    out.append((r["job_id"], js))
                else:
                    out.append((r["job_id"], json.loads(js)))
            return out
        finally:
            conn.close()


def delete_job_state(job_id: str) -> None:
    """Remove job state row (Cloud SQL or GCS)."""
    if USE_GCS_METADATA:
        _gcs_delete(f"{_GCS_JOB_STATE_PREFIX}{job_id}.json")
        return
    if not USE_CLOUD_SQL:
        return
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM job_state WHERE job_id = %s", (job_id,))
            conn.commit()
        finally:
            conn.close()
