"""Storage abstraction: resolve upload refs (local path or GCS URI) to a local Path for the pipeline."""
import tempfile
from pathlib import Path
from typing import Union

# Project root for config
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import GCS_UPLOAD_BUCKET


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
