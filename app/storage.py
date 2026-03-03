"""Storage abstraction: resolve upload refs (local path or GCS URI) to a local Path for the pipeline."""
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

# Project root for config
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import GCS_UPLOAD_BUCKET, RAG_DIR

logger = logging.getLogger("audio_pipeline.storage")


def _is_gcs_ref(ref: Union[Path, str]) -> bool:
    """True if ref is a GCS URI (gs://bucket/...)."""
    if isinstance(ref, str) and ref.startswith("gs://"):
        return True
    return False


def get_upload_path(ref: Union[Path, str]) -> Path:
    """
    Resolve an upload reference to a local file path for the pipeline.
    - If ref is a Path or local path string: return it as Path (no download).
    - If ref is a GCS URI (gs://bucket/object): download to a temp file and return that path.
    Caller is responsible for deleting the temp file after use when ref was GCS.
    """
    if isinstance(ref, Path):
        return ref
    s = str(ref).strip()
    if not _is_gcs_ref(s):
        return Path(s)
    # Download from GCS to a temp file
    from google.cloud import storage
    client = storage.Client()
    # Parse gs://bucket/path/to/object
    parts = s.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS URI: {s}")
    bucket_name, blob_name = parts[0], parts[1]
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    suffix = Path(blob_name).suffix or ".bin"
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="gcs_upload_")
    try:
        import os
        blob.download_to_filename(path)
        return Path(path)
    except Exception:
        import os
        try:
            os.close(fd)
            os.unlink(path)
        except Exception:
            pass
        raise


def upload_local_file(local_path: Path, gcs_uri: str, content_type: str | None = None) -> None:
    """
    Upload a local file to GCS. Used for writing pipeline outputs (e.g. WAV) to GCS.
    gcs_uri: e.g. gs://bucket/outputs/job_id_audio.wav
    """
    from google.cloud import storage
    s = gcs_uri.strip()
    if not s.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {s}")
    parts = s.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS URI: {s}")
    bucket_name, blob_name = parts[0], parts[1]
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path), content_type=content_type)


def delete_local_if_temp(path: Path, was_gcs: bool) -> None:
    """If path was created by get_upload_path for a GCS ref, delete the temp file."""
    if not was_gcs:
        return
    try:
        if path.is_file() and "gcs_upload_" in path.name:
            path.unlink()
    except Exception:
        pass


def upload_rag_db_to_gcs(bucket_name: str, prefix: str = "rag_db") -> tuple[str | None, str | None]:
    """
    Copy RAG_DIR to a temp dir, zip it, and upload to GCS.
    Returns (uploaded_path, latest_path) e.g. ("rag_db/rag_db_20250303T120000.zip", "rag_db/latest.zip").
    Returns (None, None) on failure (missing/empty RAG_DIR or GCS error); logs and does not raise.
    """
    if not RAG_DIR.exists() or not RAG_DIR.is_dir():
        logger.warning("upload_rag_db_to_gcs: RAG_DIR %s missing or not a directory", RAG_DIR)
        return None, None
    # Avoid listing empty dir; Chroma may have only chroma.sqlite3 and subdirs
    try:
        if not any(RAG_DIR.iterdir()):
            logger.warning("upload_rag_db_to_gcs: RAG_DIR is empty")
            return None, None
    except OSError as e:
        logger.warning("upload_rag_db_to_gcs: cannot list RAG_DIR: %s", e)
        return None, None

    tmpdir = None
    zip_path = None
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix="rag_upload_"))
        copy_dir = tmpdir / "rag_db"
        shutil.copytree(RAG_DIR, copy_dir)
        zip_path = tmpdir / "rag_db.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in copy_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(copy_dir.parent))

        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        object_name = f"{prefix.rstrip('/')}/rag_db_{timestamp}.zip"
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(zip_path), content_type="application/zip")
        latest_name = f"{prefix.rstrip('/')}/latest.zip"
        bucket.copy_blob(blob, bucket, latest_name)
        logger.info("upload_rag_db_to_gcs: uploaded %s and %s", object_name, latest_name)
        return object_name, latest_name
    except Exception as e:
        logger.exception("upload_rag_db_to_gcs failed: %s", e)
        return None, None
    finally:
        if zip_path and zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass
        if tmpdir and tmpdir.exists():
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


def restore_rag_from_gcs(bucket_name: str, blob_path: str) -> bool:
    """
    Download a RAG zip from GCS (e.g. rag_db/latest.zip), extract, and copy into RAG_DIR (overwrite).
    Returns True on success, False on failure (logs and does not raise).
    """
    from google.cloud import storage
    tmpdir = None
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            logger.warning("restore_rag_from_gcs: blob %s does not exist", blob_path)
            return False
        tmpdir = Path(tempfile.mkdtemp(prefix="rag_restore_"))
        zip_path = tmpdir / "rag_db.zip"
        blob.download_to_filename(str(zip_path))
        extract_dir = tmpdir / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        # Zip may contain top-level "rag_db/" (from upload); find the dir with chroma data
        source = extract_dir / "rag_db" if (extract_dir / "rag_db").exists() else extract_dir
        if not source.exists():
            logger.warning("restore_rag_from_gcs: no rag_db or root in zip")
            return False
        RAG_DIR.mkdir(parents=True, exist_ok=True)
        for f in source.rglob("*"):
            if f.is_file():
                rel = f.relative_to(source)
                dest = RAG_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        logger.info("restore_rag_from_gcs: restored from %s into %s", blob_path, RAG_DIR)
        return True
    except Exception as e:
        logger.exception("restore_rag_from_gcs failed: %s", e)
        return False
    finally:
        if tmpdir and tmpdir.exists():
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
