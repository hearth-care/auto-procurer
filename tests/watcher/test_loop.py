from __future__ import annotations

from xsource.watcher.loop import run_loop


def test_run_loop_calls_process_function_until_max_cycles():
    calls = []

    def process():
        calls.append("tick")
        return {"processed": 0}

    run_loop(process, poll_seconds=60, sleep_fn=lambda _: None, max_cycles=2)

    assert calls == ["tick", "tick"]
