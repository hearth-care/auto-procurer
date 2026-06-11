"""Runtime helpers shared by scheduled entry points."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xsource.obs import event


def heartbeat_payload(
    *,
    job_name: str,
    outcome: str,
    counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "job_name": job_name,
        "outcome": outcome,
        "counts": dict(counts or {}),
    }


def emit_heartbeat(
    *,
    job_name: str,
    outcome: str,
    counts: Mapping[str, Any] | None = None,
) -> None:
    event("job.heartbeat", **heartbeat_payload(job_name=job_name, outcome=outcome, counts=counts))
