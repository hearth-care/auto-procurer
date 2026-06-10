from __future__ import annotations

from xsource.watcher.loop import run_loop


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
