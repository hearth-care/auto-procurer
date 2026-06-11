"""Polling loop for the xsource watcher daemon."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class CircuitBreakerOpen(SystemExit):
    """Raised (and caught as SystemExit) when consecutive failures exceed the threshold.

    Exiting non-zero lets the supervisor (launchd KeepAlive or Cloud Run) restart
    the process visibly rather than spinning in a silent hot loop.
    """

    def __init__(self, consecutive_failures: int) -> None:
        super().__init__(1)
        self.consecutive_failures = consecutive_failures


def run_loop(
    process_once,
    *,
    poll_seconds: int,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
    on_error: Callable[[Exception], Any] | None = None,
    max_backoff_seconds: int = 300,
    breaker_threshold: int = 10,
    on_breaker_open: Callable[[int], None] | None = None,
) -> None:
    """Run ``process_once`` in a loop with exponential backoff and a circuit breaker.

    On consecutive failures the inter-cycle sleep grows as
    ``min(poll_seconds * 2**n, max_backoff_seconds)``.  After
    ``breaker_threshold`` consecutive failures the loop calls ``on_breaker_open``
    and raises ``CircuitBreakerOpen`` (a ``SystemExit`` subclass) so the
    supervisor restarts the process rather than spinning indefinitely.

    ``sleep_fn`` is injected for tests.  ``max_cycles`` caps iteration count.
    """
    cycles = 0
    consecutive_failures = 0

    while True:
        try:
            process_once()
            consecutive_failures = 0
            sleep_seconds: float = poll_seconds
        except Exception as exc:
            consecutive_failures += 1
            if on_error is None:
                raise
            on_error(exc)
            if consecutive_failures >= breaker_threshold:
                if on_breaker_open is not None:
                    on_breaker_open(consecutive_failures)
                raise CircuitBreakerOpen(consecutive_failures) from exc
            backoff = min(poll_seconds * (2 ** (consecutive_failures - 1)), max_backoff_seconds)
            sleep_seconds = float(backoff)

        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return
        sleep_fn(sleep_seconds)
