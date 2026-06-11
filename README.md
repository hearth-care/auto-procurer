# Auto-Procurer (xsource)

A Clonway fleet worker, scaffolded from
[clonway-cockpit](https://github.com/hearth-care/clonway-cockpit)'s worker
template (S8/C6). It is **born with**:

- an interactive **cockpit** — `xsource` (bare, on a TTY) opens the
  three-region shell (pulse / needs-you / toolkit) with one example capability,
  a pulse stub, and a Doctor stub;
- a flag-guarded **Signal emit** path (`xsource signals scan`, gated on
  `XSOURCE_EMIT_SIGNALS`, default OFF) that writes the C0 wire shape to
  `signals/xsource/latest.jsonl`;
- a **mandatory** `@scan_horizon` stub (`scan_xsource_horizon`) — a
  worker can't exist without at least an empty forward scan (proactive by
  construction), guarded by an `xfail` test until you fill it in;
- run/stage **telemetry** (`xsource.obs`) to the xops dashboard;
- the single **write-gate + draft-never-send** safety posture, inherited from
  the framework;
- **CI** (ruff + mypy + pytest).

## Quick start

```bash
uv sync
uv run xsource signals scan                  # -> disabled (flag off)
XSOURCE_EMIT_SIGNALS=1 uv run xsource signals scan  # -> emitted 0 (no horizon yet)
uv run pytest -q && uv run ruff check .              # green out of the box
```

## Runtime

Production runtime is Cloud Run jobs plus Cloud Scheduler:

- `xsource watcher run --cycles 4 --interval 60` every five minutes;
- `xsource request sync-all` nightly;
- `xsource signals scan` daily.

Deployment uses `.github/workflows/deploy-cloud-run.yml` and config keys from
`deploy/xsource-cloud-run.env.example`. Secret values are mounted as files so
the existing `XSOURCE_GMAIL_TOKEN_PATH`, `XSOURCE_SHEETS_TOKEN_PATH`, and
`*_FILE` API-key conventions keep working. State that used to live in the Mac
state directory is hydrated from `XSOURCE_FLEET_BUCKET` / `XSOURCE_STATE_PREFIX`
at job start and uploaded after mutation.

Cutover, soak, decommission, and rollback steps live in
`docs/runbooks/cloud-run-cutover.md`. `scripts/install_launchd.py` is retained
for rollback only; do not use it for steady-state production scheduling.
Use `scripts/cutover_launchd.py` to archive, unload, or restore legacy launchd
jobs.

## Make it real

1. **`src/xsource/signals/build.py`** — replace the empty
   `scan_xsource_horizon` stub with real forward-looking Signals from
   live domain state, each with a real `due_at`. Add more `@scan_horizon`
   functions and list them in `compose_horizon(...)`. Then flip the
   `xfail` test in `tests/test_signals_build.py` to assert your real signals.
2. **`src/xsource/cli/cockpit.py`** — replace the example capability,
   the pulse stub, the Doctor probes, and `capture_state()` with real
   xsource surfaces.
3. **Go live** — register `xsource` in the bridge roster
   (`Auto-Orchestrator/src/xops/bridge/workers.py`), set `XSOURCE_EMIT_SIGNALS=1`, and
   add a daily `signals scan` scheduler entry (see clonway-cockpit's
   `docs/onboarding-a-worker.md` §5–6 for the per-shape recipe).

## Pull template improvements

```bash
copier update   # re-applies clonway-cockpit's worker-template; your filled-in
                # domain code is preserved (see the template's _exclude).
```
