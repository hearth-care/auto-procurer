from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

from clonway_cockpit.signals.model import Signal

def emit_signals(
    *,
    worker_id: str,
    flag_env: str,
    build: Callable[..., Sequence[Signal]],
    bucket: str = ...,
    project: str | None = None,
    now: datetime | None = None,
    today: date | None = None,
    run_id: str | None = None,
    storage_client_factory: Callable[[], Any] | None = None,
) -> tuple[Signal, ...]: ...
def flag_enabled(flag: str) -> bool: ...
