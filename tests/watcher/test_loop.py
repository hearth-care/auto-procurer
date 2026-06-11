from __future__ import annotations

import pytest

from xsource.watcher.loop import CircuitBreakerOpen, run_loop


def test_run_loop_calls_process_function_until_max_cycles():
    calls = []

    def process():
        calls.append("tick")
        return {"processed": 0}

    run_loop(process, poll_seconds=60, sleep_fn=lambda _: None, max_cycles=2)

    assert calls == ["tick", "tick"]


def test_run_loop_continues_after_process_exception():
    calls = []
    errors = []

    def process():
        calls.append("tick")
        if len(calls) == 1:
            raise RuntimeError("simulated gmail outage")
        return {"processed": 0}

    run_loop(
        process,
        poll_seconds=60,
        sleep_fn=lambda _: None,
        max_cycles=2,
        on_error=lambda exc: errors.append(str(exc)),
    )

    assert calls == ["tick", "tick"]
    assert errors == ["simulated gmail outage"]


def test_run_loop_backoff_grows_on_consecutive_failures():
    sleeps = []

    def always_fail():
        raise RuntimeError("outage")

    with pytest.raises(CircuitBreakerOpen):
        run_loop(
            always_fail,
            poll_seconds=10,
            max_backoff_seconds=100,
            breaker_threshold=5,
            sleep_fn=sleeps.append,
            on_error=lambda exc: None,
        )

    # sleeps: after failure 1: 10*(2**0)=10, failure 2: 20, failure 3: 40,
    # failure 4: 80 — breaker fires on failure 5 without an extra sleep.
    assert sleeps == [10, 20, 40, 80]
    assert all(s <= 100 for s in sleeps)


def test_run_loop_backoff_capped_at_max_backoff():
    sleeps = []

    def always_fail():
        raise RuntimeError("outage")

    with pytest.raises(CircuitBreakerOpen):
        run_loop(
            always_fail,
            poll_seconds=60,
            max_backoff_seconds=120,
            breaker_threshold=5,
            sleep_fn=sleeps.append,
            on_error=lambda exc: None,
        )

    # 60, 120, 120, 120 (capped at 120) — breaker opens on 5th failure
    assert sleeps[1] == 120
    assert all(s <= 120 for s in sleeps)


def test_run_loop_backoff_resets_after_success():
    sleeps = []
    calls = []

    def alternating():
        calls.append(len(calls))
        # fail on calls 0-1, succeed on call 2, fail on call 3
        if len(calls) in (1, 2):
            raise RuntimeError("transient")
        return {}

    run_loop(
        alternating,
        poll_seconds=10,
        max_backoff_seconds=200,
        breaker_threshold=10,
        max_cycles=4,
        sleep_fn=sleeps.append,
        on_error=lambda exc: None,
    )

    # After success on cycle 3, next sleep should reset to base poll_seconds=10
    assert sleeps[2] == 10


def test_run_loop_breaker_opens_after_threshold():
    breaker_events = []

    def always_fail():
        raise RuntimeError("persistent failure")

    with pytest.raises(CircuitBreakerOpen) as exc_info:
        run_loop(
            always_fail,
            poll_seconds=1,
            breaker_threshold=3,
            sleep_fn=lambda _: None,
            on_error=lambda exc: None,
            on_breaker_open=lambda n: breaker_events.append(n),
        )

    assert exc_info.value.consecutive_failures == 3
    assert breaker_events == [3]


def test_run_loop_breaker_not_triggered_with_enough_successes():
    """Breaker should not open if failures are separated by successes."""
    calls = [0]
    errors = []

    def flaky():
        calls[0] += 1
        # fail only on odd cycles — never consecutive enough to trip breaker
        if calls[0] % 2 == 1:
            raise RuntimeError("odd fail")
        return {}

    run_loop(
        flaky,
        poll_seconds=1,
        breaker_threshold=5,
        max_cycles=8,
        sleep_fn=lambda _: None,
        on_error=lambda exc: errors.append(str(exc)),
    )

    assert calls[0] == 8
