"""GCS heartbeat writer for xsource Cloud Run jobs.

Each scheduled job calls ``write_heartbeat`` once on completion — ok=True on
success, ok=False on failure. Blobs land at::

    heartbeats/{job_id}/latest.json

in the shared fleet bucket.  Best-effort: never crashes the caller.

Copied from the xops beat.py pattern — do NOT import from xops.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_BUCKET = "clonway-orchestrator-eu-west2"


def _default_bucket() -> str:
    return os.environ.get("XSOURCE_GCS_BUCKET", _BUCKET)


def _storage_client():
    """Lazy ADC-backed storage client; tests patch this seam."""
    from google.cloud import storage

    return storage.Client()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def write_heartbeat(job_id: str, *, ok: bool, detail: str = "", bucket: str | None = None) -> bool:
    """Write the latest heartbeat for one job.

    Best-effort — never crashes the caller.  Returns True on success, False if
    the GCS write failed (caller can log but must not raise).
    """
    target_bucket = bucket or _default_bucket()
    object_name = f"heartbeats/{job_id}/latest.json"
    payload = {
        "job_id": job_id,
        "ran_at": _utc_now().isoformat(),
        "ok": ok,
        "host": platform.node(),
        "detail": detail,
    }
    try:
        client = _storage_client()
        client.bucket(target_bucket).blob(object_name).upload_from_string(
            json.dumps(payload),
            content_type="application/json",
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "heartbeat write failed for %s/%s", target_bucket, object_name, exc_info=True
        )
        return False
    return True
