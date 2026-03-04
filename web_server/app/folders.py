"""Read-only folders from GCS output bucket (metadata/folders.json). Same layout as main app USE_GCS_METADATA."""
import json
import logging
from typing import Any

from config import GCS_OUTPUT_BUCKET

logger = logging.getLogger("web_server.folders")

_GCS_FOLDERS_KEY = "metadata/folders.json"


def _bucket():
    if not GCS_OUTPUT_BUCKET:
        return None
    from google.cloud import storage
    return storage.Client().bucket(GCS_OUTPUT_BUCKET)


def list_folders() -> list[dict[str, Any]]:
    """Return all folders from metadata/folders.json in the output bucket. Empty list if not configured."""
    bucket = _bucket()
    if not bucket:
        return []
    try:
        blob = bucket.blob(_GCS_FOLDERS_KEY)
        if not blob.exists():
            return []
        data = json.loads(blob.download_as_string().decode("utf-8"))
        folders = (data.get("folders") or []) if isinstance(data, dict) else []
        return sorted(folders, key=lambda r: (r.get("name") or "").lower())
    except Exception as e:
        logger.warning("list_folders failed: %s", e)
        return []
