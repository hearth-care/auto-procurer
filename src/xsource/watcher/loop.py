"""Polling loop for the xsource watcher daemon."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def run_loop(
    process_once,
    *,
    poll_seconds: int,
    sleep_fn: Callable[[int], None] = time.sleep,
    max_cycles: int | None = None,
    on_error: Callable[[Exception], Any] | None = None,
) -> None:
    cycles = 0
    while True:
        try:
            process_once()
        except Exception as exc:
            if on_error is None:
                raise
            on_error(exc)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return
        sleep_fn(poll_seconds)
