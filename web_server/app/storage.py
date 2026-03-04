"""Storage: restore RAG from GCS, upload RAG to GCS. Same bucket layout: job_state/, outputs/, rag_db/."""
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import RAG_DIR

logger = logging.getLogger("web_server.storage")


def upload_rag_db_to_gcs(
    bucket_name: str,
    prefix: str = "rag_db",
    progress_callback=None,
) -> tuple[str | None, str | None]:
    """
    Zip RAG_DIR and upload to GCS. Returns (uploaded_path, latest_path) or (None, None).
    progress_callback: optional callable(message: str) for progress updates during zip/upload.
    """
    def progress(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)
        logger.info("upload_rag_db_to_gcs: %s", msg)

    if not RAG_DIR.exists() or not RAG_DIR.is_dir():
        logger.warning("upload_rag_db_to_gcs: RAG_DIR %s missing or not a directory", RAG_DIR)
        if progress_callback:
            progress_callback(f"RAG upload failed: RAG_DIR {RAG_DIR} missing or not a directory.")
        return None, None
    try:
        if not any(RAG_DIR.iterdir()):
            logger.warning("upload_rag_db_to_gcs: RAG_DIR is empty")
            if progress_callback:
                progress_callback("RAG upload failed: RAG directory is empty.")
            return None, None
    except OSError as e:
        logger.warning("upload_rag_db_to_gcs: cannot list RAG_DIR: %s", e)
        if progress_callback:
            progress_callback(f"RAG upload failed: cannot list RAG directory: {e}")
        return None, None

    tmpdir = None
    zip_path = None
    try:
        progress("Zipping RAG…")
        tmpdir = Path(tempfile.mkdtemp(prefix="rag_upload_"))
        copy_dir = tmpdir / "rag_db"
        shutil.copytree(RAG_DIR, copy_dir)
        zip_path = tmpdir / "rag_db.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in copy_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(copy_dir.parent))

        progress("Uploading zip to GCS (this may take several minutes for large RAG)…")
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        object_name = f"{prefix.rstrip('/')}/rag_db_{timestamp}.zip"
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(zip_path), content_type="application/zip")
        progress("Updating latest.zip in bucket…")
        latest_name = f"{prefix.rstrip('/')}/latest.zip"
        bucket.copy_blob(blob, bucket, latest_name)
        logger.info("upload_rag_db_to_gcs: uploaded %s and %s", object_name, latest_name)
        return object_name, latest_name
    except Exception as e:
        msg = f"RAG upload failed: {e}"
        logger.exception("upload_rag_db_to_gcs failed: %s", e)
        if progress_callback:
            progress_callback(msg)
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


def _extract_rag_zip_to_dir(zip_path: Path, extract_dir: Path) -> bool:
    """Extract RAG zip into extract_dir; copy into RAG_DIR."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    source = extract_dir / "rag_db" if (extract_dir / "rag_db").exists() else extract_dir
    if not source.exists():
        return False
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    for f in source.rglob("*"):
        if f.is_file():
            rel = f.relative_to(source)
            dest = RAG_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    return True


def restore_rag_from_gcs(bucket_name: str, blob_path: str) -> bool:
    """Download RAG zip from GCS (e.g. rag_db/latest.zip), extract into RAG_DIR. Returns True on success."""
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
        if not _extract_rag_zip_to_dir(zip_path, extract_dir):
            logger.warning("restore_rag_from_gcs: no rag_db or root in zip")
            return False
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
