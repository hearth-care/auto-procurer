# Auto-Procurer (xsource)

A Clonway fleet worker that automates procurement: sourcing local suppliers,
drafting outreach, tracking quote replies, and surfacing chase or reorder
Signals to the fleet. The cockpit (interactive TUI) and the agent mode
(`--agent-stdio`) share a single code path.

## Quick start

```bash
uv sync
uv run xsource --help

# Cockpit (interactive TTY)
uv run xsource

# Signals (flag off by default)
uv run xsource signals scan
# -> signals: disabled (set XSOURCE_EMIT_SIGNALS=1 to enable)

XSOURCE_EMIT_SIGNALS=1 uv run xsource signals scan
# -> emitted N   (or emitted 0 if no horizon items are due today)
```

## CLI surface

```
xsource signals scan          # build and emit forward-item Signals
xsource watcher run           # poll Gmail for supplier replies (loop)
xsource watcher status        # show watcher state / last-seen thread IDs
xsource request sync          # sync a single request record from the Sheet
xsource request sync-all      # sync all open request records
xsource request trigger       # parse an email/chat trigger and show extraction
xsource request followup      # draft a follow-up reply for a supplier response
xsource request reorder       # open a prefilled reorder review for a recurring supplier
```

`xsource` bare on a TTY opens the cockpit. `xsource --agent-stdio` serves it
over JSON stdin/stdout for agent callers.

## Cockpit

The cockpit is a three-region shell (pulse / needs-you / toolkit) with the
following shelves:

| Shelf | Label | What it does |
|-------|-------|--------------|
| A | New request | Research and shortlist suppliers for a new procurement need |
| B | Requests | Browse and manage open requests |
| C | Black book | Search the supplier database |
| D | Publish | Publish a shortlist to Google Sheets and share with staff |
| E | Outreach | Draft Gmail outreach to shortlisted suppliers (never sends) |
| G | Diagnostics & setup | Doctor probes: config, credentials, store, budget |

**Write-gate / draft-never-send posture.** All write paths go through the
`confirm_apply` gate. In agent mode (`--agent-stdio`) the cockpit is dry-run
by default; applying requires the explicit `--allow-apply` handshake. The
outreach shelf creates Gmail _drafts_ and records draft/thread IDs — it does
not send email.

## Signals

`xsource signals scan` calls `scan_xsource_horizon`, composed from four
horizon builders:

- `build_chase_quote_signals` — emits a chase signal for any open request
  where all shortlisted suppliers were asked but none have replied and the
  chase window (`XSOURCE_CHASE_AFTER_DAYS`, default 3) has elapsed.
- `build_recurring_service_signals` — emits a reorder reminder when a
  recurring supplier's next-due date is within 21 days.
- `build_watcher_health_signals` — emits a warning when a thread has been
  open for more than one watcher poll cycle with no reply seen.
- `build_store_offline_signals` — emits an alert when the GCS store is
  offline and there are open requests that need attention.

`XSOURCE_EMIT_SIGNALS=1` enables the flag; leaving it unset prints
`signals: disabled`. `emitted 0` means no horizon items are due today
based on live data — not a missing implementation.

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

## Configuration

All knobs are environment variables. Required values are checked by the Doctor
shelf (G) at cockpit start.

| Variable | Required | Default | What happens when absent |
|----------|----------|---------|--------------------------|
| `GOOGLE_MAPS_API_KEY` | yes | — | Research preflight blocks (no place search) |
| `ANTHROPIC_API_KEY` | yes | — | Research and outreach preflight blocks |
| `XSOURCE_SHEETS_TOKEN_PATH` | yes | — | Publish/sync disabled; Doctor shows missing |
| `XSOURCE_GMAIL_TOKEN_PATH` | yes (outreach) | — | Outreach preflight blocks; watcher cannot poll |
| `XSOURCE_HOME_POSTCODE` | yes | — | Radius search has no anchor; Doctor shows missing |
| `XSOURCE_FLEET_BUCKET` | yes (Cloud Run) | — | Falls back to local state dir; offline in Cloud Run |
| `XSOURCE_EMIT_SIGNALS` | no | unset (off) | `signals scan` prints disabled and exits |
| `XSOURCE_MONTHLY_BUDGET_GBP` | no | `10` | Research allowed up to £10/month |
| `XSOURCE_DEFAULT_RADIUS_MILES` | no | `15` | Supplier search radius |
| `XSOURCE_CHASE_AFTER_DAYS` | no | `3` | Days before a chase signal fires |
| `XSOURCE_MODEL_CHAIN` | no | `claude-sonnet-4-6` | Comma-separated model fallback chain |
| `XSOURCE_STATE_PREFIX` | no | `state/xsource` | GCS prefix for state objects |
| `XSOURCE_DRIVE_FOLDER_ID` | no | — | Google Drive folder for published shortlists |
| `XSOURCE_STAFF_SHARE_GROUP` | no | — | Google Group address to share published sheets with |

In Cloud Run, secrets are mounted as files; the `*_TOKEN_PATH` and `*_FILE`
env vars point to those mount paths. See `deploy/xsource-cloud-run.env.example`
for the full variable list including Cloud Run–specific scheduler and job names.

## Development

```bash
uv sync
uv run pytest -q          # full test suite
uv run ruff check .       # linting
uv run ruff format .      # formatting
```

Pre-commit runs ruff, ruff-format, and mypy on every commit. The full pytest
suite is the CI gate — run it locally on demand, not on every commit.
