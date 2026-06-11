# [Plan] Migrate xsource off Mac-local launchd

**Status:** implementation in progress on PR #15
**Source:** fleet audit 2026-06-11, item O9 (context: audit §3 Mac-local
estate findings, dragon D3)
**Wave:** 2

xsource's production runtime today is three launchd jobs on the operator's
personal Mac. If the machine sleeps, shuts down, or loses its login session,
procurement silently stops: replies go unwatched, Sheets unsynced, signals
unemitted — and nothing in the fleet's cloud monitoring can see it. The audit
ranks Mac-local production as a top-three fleet dragon (D3). This plan moves
xsource's scheduled runtime to Cloud Run in the fleet's shared GCP project,
migrates credentials to Secret Manager, closes the local-only state gaps, adds
heartbeat emission, and decommissions the launchd jobs with a tested rollback.

## Why

Every claim was re-verified against `origin/main` (`ebfd22a`) on 2026-06-11.

- **Production = three launchd jobs** (`scripts/install_launchd.py:52-70`):
  - `…xsource.watcher` — `xsource watcher run`, every 60s (`start_interval=60`);
  - `…xsource.sync` — `xsource request sync-all`, nightly 02:10;
  - `…xsource.signals` — `xsource signals scan`, daily 07:05.
  Logs go only to `~/Library/Logs/<label>.{out,err}.log`
  (`install_launchd.py:32-34`) — invisible to cloud monitoring.
- **The code already expects this to be temporary.**
  `src/xsource/obs.py:28` — `_RUNTIME_ENV = None  # launchd daemon — no Cloud
  Logging mirror`; `src/xsource/signals/emit.py:28-30` pins a GCP project
  constant purely because "a launchd daemon's env is HOME-only" — both are
  launchd workarounds that Cloud Run's ambient ADC/metadata make unnecessary.
- **Primary state is already cloud-synced — verified, with two gaps.**
  `src/xsource/wiring.py:21-28` — suppliers and requests live in `SyncedStore`s
  that download from / upload to objects under the fleet's orchestrator bucket
  (`_BUCKET`, `wiring.py:18`), so the canonical store survives a machine loss.
  But two pieces of state are local-only and would be lost or forked by a
  naive migration:
  1. the watcher's processed-message dedup DB —
     `src/xsource/cli/watcher.py:57` (`watcher.sqlite3` under
     `Config.state_dir`); losing it re-processes old messages, splitting it
     across two runners double-processes;
  2. the monthly research-budget ledger — `src/xsource/budget.py:12`
     (`budget-<month>.json` under `state_dir`); losing it silently resets the
     spend cap.
- **Credentials are files/env on the Mac.**
  `src/xsource/cli/watcher.py:38,45` — Gmail and Sheets OAuth user tokens are
  read with `Credentials.from_authorized_user_file` from paths in
  `XSOURCE_GMAIL_TOKEN_PATH` / `XSOURCE_SHEETS_TOKEN_PATH`; API keys arrive via
  env or `*_FILE` (`src/xsource/secrets.py`). The launchd installer embeds env
  into plists and at least refuses a raw Anthropic key
  (`install_launchd.py:15,102`), but everything ultimately lives on one
  laptop's disk.
- **Interim mitigation exists fleet-side, not here:** heartbeat meta-signals
  for the Mac-local estate (audit item O5) are specified in the orchestrator
  repo's mac-estate-heartbeats plan, so a sleeping Mac at least becomes visible
  in the morning briefing. That mitigates detection, not availability — this
  plan removes the single point of failure itself.

## Scope

In scope:

- containerising xsource and deploying its three schedules to Cloud Run in the
  fleet's shared GCP project/region (read from the fleet config file's keys,
  not hardcoded)
- the watcher job-vs-service decision (trade-off below, with recommendation)
- credentials → Secret Manager (tokens + API keys), with a no-code-change
  delivery mechanism preferred
- closing the two local-state gaps (dedup DB, budget ledger)
- heartbeat emission so the fleet can alarm on a silent stop
- launchd decommission procedure + rollback

Out of scope:

- watcher retry/backoff + circuit breaker internals (separate plan in this
  series: `2026-06-fleet-audit-hygiene-resilience.md`; its
  exit-non-zero-on-breaker design is intentionally Cloud-Run-friendly)
- the orchestrator-side heartbeat consumption (O5, tracked in that repo)
- any change to what xsource *does* — this is a runtime move, not a feature

## Spec

### Deployment shape

**Trade-off — watcher as always-on service vs scheduled job:**

| | Always-on Cloud Run service (min-instances=1, runs `run_loop`) | Cloud Scheduler → Cloud Run job (batched `--once` cycles) |
|---|---|---|
| Latency to a reply | ~60s (current parity) | up to schedule interval (min 1 min; practical 5–10 min) |
| Cost | always-on instance, billed continuously | seconds of CPU per run |
| Failure visibility | crash-loop visible; silent hang possible | every execution has a success/fail status — alertable |
| Idempotency pressure | low (one process) | must be safe if runs overlap or double-fire |
| Fleet precedent | the always-on services in the fleet are request-serving, not pollers | sibling workers' periodic work is scheduler+job shaped |

**Recommendation:** scheduled **job** every 5 minutes executing a bounded batch
(e.g. `xsource watcher run --cycles 4 --interval 60`, a small extension of the
existing `--once`), because: reply-to-supplier-quote latency tolerance is
minutes-to-hours, not seconds; per-execution status gives exactly the
visibility the Mac never had; and the dedup store already makes reprocessing
safe. The always-on service remains the fallback if observed latency
disappoints — note the decision explicitly in the PR that implements it.

Sync (nightly) and signals (daily) map 1:1 to Cloud Scheduler → Cloud Run job
executions at their current times.

**Container:** one image for all three entry points (args select the command),
built from a standard Python/uv Dockerfile, deployed by a GitHub Actions
workflow mirroring the sibling workers' deploy jobs. Runtime identity is a
dedicated per-worker service account with least privilege: objects under this
worker's prefixes in the orchestrator bucket, its Secret Manager secrets, and
nothing else.

### Credential migration

- Gmail token, Sheets token: one Secret Manager secret each, **mounted as
  files** via Cloud Run volume mounts so `XSOURCE_GMAIL_TOKEN_PATH` /
  `XSOURCE_SHEETS_TOKEN_PATH` point at the mounts and *no application code
  changes*. The existing `*_FILE` convention (`secrets.py`) covers the API
  keys the same way.
- Token refresh: `google-auth` refreshes access tokens in memory from the
  long-lived refresh token, and the current code never writes the token file
  back — verify this holds (no `to_json` persistence needed) during the spike;
  if Google rotates a refresh token, re-provisioning is an operator runbook
  step (documented in the migration runbook).
- The operator provisions secret *values* (the OAuth consent flows still run
  on a trusted machine); scripts in this repo only create/update secret
  containers and bindings, printing every command first per fleet convention.
- `signals/emit.py` `_PROJECT` pin and `obs.py` `_RUNTIME_ENV = None` become
  environment-derived (project from ADC; runtime env set in the Cloud Run
  spec), keeping local-dev behaviour unchanged.

### State gaps

- **Dedup DB:** smallest viable fix — download/upload `watcher.sqlite3` around
  each watcher execution via the same blob pattern as `SyncedStore`
  (single-writer is guaranteed by the one schedule; document that). A schema
  move of dedup state into the request records is noted as a cleaner future
  option but is not required to migrate.
- **Budget ledger:** same blob-sync treatment for `budget-<month>.json`
  (read-modify-write is rare and operator-driven research is the only writer).
- `Config.state_dir` keeps working: on Cloud Run it is ephemeral scratch that
  is hydrated from GCS at start (the `SyncedStore` constructor already does
  this for the two main stores).

### Heartbeats

- Each scheduled execution wraps in the existing `obs.run_session`, which
  already flushes run logs to the fleet bucket — on Cloud Run this starts
  working with ADC where on launchd it degraded silently without creds.
- Add an explicit per-run heartbeat event (job name, outcome, counts) so the
  orchestrator's briefing can distinguish "ran and found nothing" from "did
  not run" — the same contract the fleet's mac-estate-heartbeats plan
  establishes, emitted natively from Cloud Run instead of from launchd.
- Watcher-staleness already self-reports via
  `build_watcher_health_signals` (`src/xsource/signals/build.py:167-205`);
  after migration its 2-hour staleness window should comfortably hold.

### Decommission + rollback

Cutover order (each step reversible):

1. Deploy jobs + schedulers **paused**; run each job once manually; verify
   store writes, Sheet updates, signal emission, heartbeats.
2. Enable cloud schedulers; **leave launchd jobs running** for a 3-day soak —
   double-running is safe for sync/signals (idempotent overwrites) and the
   shared dedup DB question makes the watcher the exception: keep the *cloud*
   watcher paused OR unload the local watcher first; never run both.
3. Unload launchd: `launchctl bootout gui/<uid> <plist>` for each label;
   archive the plists and the env file rather than deleting.
4. Soak one week on cloud-only; then remove plists and rotate any credentials
   that lived in the launchd env file.

Rollback at any step: pause cloud schedulers, re-`bootstrap` the archived
plists — the GCS-synced stores mean state follows whichever runner is active.

## Implementation plan

### Phase 1 — containerise + deploy skeleton (M)

- [x] `Dockerfile` + `.dockerignore`; image runs `xsource --help` healthily.
- [x] Deploy workflow (build/push/deploy) mirroring sibling workers; jobs
      created with schedulers **paused**; per-worker runtime SA.
- [x] Fleet config file gains this worker's entries (service/job names,
      bucket prefixes, SA) — referenced by key, values stay out of this repo.
- Tests: CI builds the image; a smoke job execution exits 0 with no-op env.

### Phase 2 — secrets + config (M)

- [ ] Secret containers + volume mounts for both OAuth tokens and API keys;
      Cloud Run env sets the existing `*_PATH`/`*_FILE` variables.
- [ ] `signals/emit.py` project pin and `obs.py` runtime env become
      environment-derived with launchd-compatible fallbacks.
- [ ] Operator script (stdlib-only, idempotent, prints every command) to
      create bindings; token-provisioning runbook section.
- Tests: unit tests for env-derived project/runtime fallbacks; manual job run
  reads all credentials from mounts.

### Phase 3 — state gaps + batched watcher (M)

- [ ] Blob-sync wrappers for `watcher.sqlite3` and the budget ledger.
- [ ] `watcher run --cycles N --interval S` bounded-batch mode (builds on the
      existing `--once` and `run_loop(max_cycles=…)` seams,
      `src/xsource/watcher/loop.py:14`).
- [ ] Heartbeat event in each entry point's `run_session`.
- Tests: dedup DB round-trip; batch mode runs N cycles then exits; heartbeat
  payload shape.

### Phase 4 — cutover + decommission (S, operational)

- [ ] Manual verification runs; enable sync+signals schedulers; soak.
- [ ] Watcher single-runner cutover (unload local watcher, enable cloud).
- [ ] `launchctl bootout` all three; archive plists; rotate env-file creds.
- [ ] Update `README.md` runtime section; mark
      `scripts/install_launchd.py` as legacy/rollback-only in its docstring.
- Acceptance: one week cloud-only with green executions and heartbeats.

## Acceptance criteria

- [ ] All three schedules run as Cloud Run jobs in the fleet project with
      per-execution success/failure visible in cloud monitoring.
- [ ] No credential or token file is required on (or read from) the operator's
      Mac for steady-state operation.
- [ ] Replies processed exactly once across the cutover (dedup DB migrated,
      single-runner rule observed); budget ledger continuity preserved.
- [ ] Every execution emits a heartbeat the orchestrator can consume; a
      skipped/failed execution is distinguishable from a quiet one.
- [ ] launchd jobs unloaded and archived; documented rollback re-establishes
      local operation in under 15 minutes.
- [ ] No behavioural change to procurement logic; full test suite green; the
      draft-only/never-send posture untouched.

## Risks & dependencies

- **Gmail/Sheets OAuth from cloud IPs:** user-credential refresh generally
  works from anywhere, but verify early (Phase 2 manual run) — Google may
  flag unusual-location refreshes; the runbook covers re-consent.
- **Refresh-token rotation:** if Google rotates the refresh token, the
  mounted secret goes stale silently → auth failures. Mitigation: the
  watcher-stale signal + per-execution failures make this loud; runbook step
  to re-provision.
- **Double-running the watcher** during cutover double-processes replies; the
  cutover order above makes the single-runner rule explicit.
- **Dedup-DB blob sync races:** safe only under one scheduled runner; if the
  schedule is ever fanned out, the dedup state must move into the request
  store first (noted in spec).
- **Cost:** scheduled-job shape is near-zero; revisit only if the always-on
  service fallback is taken.
- **Dependencies:** fleet GCP project/Scheduler provisioning rights; operator
  time for secret provisioning and the soak; the orchestrator-side heartbeat
  consumer (O5) lands independently — heartbeats are useful logs even before
  it does; coordination with the hygiene-resilience plan (breaker exit codes
  align with job-failure semantics).

## Next-agent pickup

1. Branch off `main`; do not stack on this planning branch.
2. Re-verify citations against current `main` and the live launchd state
   (`launchctl list | grep xsource` on the operator's Mac) before Phase 4.
3. Phases 1–3 are pure-repo and shippable as PRs; Phase 4 is operational and
   needs operator participation (secret values, cutover windows) — hand them a
   single-paste runbook script per fleet convention, not command sequences.
4. Run `uv run pytest -q`, `uv run ruff check .`, `uv run mypy` before each PR.
5. Public repo: keep project ids, bucket names, SA emails, and scheduler URIs
   out of code and docs — read them from the fleet config file (reference its
   keys) or from deployment-time env.

## HANDOFF NOTES

- Agent: builder-codex-20260611T200954Z-94309.
- Current phase: Phase 2 next. Phase 1 repo artefacts are implemented in this PR branch.
- Decisions taken: watcher uses scheduled Cloud Run job with `xsource watcher run --cycles 4 --interval 60`; deploy workflow creates schedulers paused and reads concrete fleet values from repo environment variables/secrets, not checked-in docs.
- Verification so far: `uv run pytest tests/deploy/test_cloud_run_phase1.py -q` -> 3 passed.
- Known failing tests: none from the current targeted slice.
