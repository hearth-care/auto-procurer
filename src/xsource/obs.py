"""Run/stage telemetry for xsource — a thin shim over the shared emitter.

Binds ``worker_id="xsource"`` (+ a ``reserved_prefix`` and the runtime
env var) to ``clonway_cockpit.obs.make_obs`` and re-exports the resulting
``event`` / ``run_session``. The wire shape, paths, run_id resolution,
reserved-key renaming, and degrade behaviour all live in the shared core — this
worker is byte-identical on the xops dashboard.

* ``event(name, severity=…, **fields)`` — emit one structured event. Always
  fires a local stdlib log line; buffered into the active run's JSONL flush.
* ``run_session(trigger=…, args=…)`` — wraps a run: ``run.started`` … yield …
  ``run.finished`` + a JSONL flush to the fleet logs bucket.

Both degrade silently with no creds (local/dev) — observability never breaks a
worker run.
"""

from __future__ import annotations

from clonway_cockpit import obs as _obs

_WORKER_ID = "xsource"
_RUNTIME_ENV = "XSOURCE_RUNTIME_ENV"

# ``reserved_prefix="f_"`` matches xhr/xletter/xquill (xbook uses "field_"); pick
# whichever your greppable log conventions expect. The shared core renames any
# caller field that collides with a LogRecord attribute, prefixed with this.
event, run_session = _obs.make_obs(
    worker_id=_WORKER_ID,
    runtime_env=_RUNTIME_ENV,
    reserved_prefix="f_",
)

__all__ = ["event", "run_session"]
