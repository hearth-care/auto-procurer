from __future__ import annotations

from xsource.runtime import heartbeat_payload


def test_heartbeat_payload_shape() -> None:
    payload = heartbeat_payload(
        job_name="watcher",
        outcome="ok",
        counts={"processed": 2, "possible_replies": 1},
    )

    assert payload == {
        "job_name": "watcher",
        "outcome": "ok",
        "counts": {"processed": 2, "possible_replies": 1},
    }
