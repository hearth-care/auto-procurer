# xsource Cloud Run cutover runbook

This runbook moves xsource from legacy launchd jobs to Cloud Run jobs. It keeps
all concrete project ids, buckets, service-account names, and secret names in
deployment environment variables, not in this repo.

## OPERATOR TODO before cutover

- Fill the deployment environment keys from `deploy/xsource-cloud-run.env.example`.
- Provision OAuth token and API key secret values after the secret containers
  exist. Do not pass token JSON or URLs as CLI arguments.
- Confirm the fleet heartbeat consumer is ready to read `job.heartbeat` events,
  or accept that heartbeats are available in run logs until that consumer lands.
- Pick the watcher cutover window. During soak, never run both watchers.

## Provision secret containers and bindings

Run the paste-safe helper, then add the secret values through the trusted local
secret-value flow:

```bash
python3 /Users/olliepage/Developer/Auto-Procurer/scripts/provision_cloud_run.py
```

Use `--apply` only after the dry-run output is reviewed.

## Deploy jobs and schedulers paused

Run the `Deploy Cloud Run jobs` GitHub workflow from this PR branch. The workflow:

- builds one container image;
- deploys watcher, sync, and signals Cloud Run jobs;
- creates Scheduler jobs for the three schedules;
- pauses every Scheduler job before returning.

Manual verification while paused:

- watcher job: bounded run exits 0 and writes the synced watcher DB;
- sync job: reads the mounted Sheets token and updates request state;
- signals job: emits signals and a heartbeat when `XSOURCE_EMIT_SIGNALS=1`;
- each job emits `job.heartbeat` with `job_name`, `outcome`, and `counts`.

## Soak

- Enable sync and signals schedulers first.
- Leave local sync/signals launchd running for the initial soak only if their
  idempotent writes are acceptable for the window.
- For watcher, choose exactly one runner. Keep the cloud watcher paused until
  local watcher is unloaded, or unload local watcher before enabling cloud.
  The rule is: never run both watchers.
- Soak for three days with green Cloud Run executions and heartbeat evidence.

## Decommission launchd

Use the helper rather than pasting several `launchctl bootout` commands:

```bash
python3 /Users/olliepage/Developer/Auto-Procurer/scripts/cutover_launchd.py bootout
```

Review the dry-run output first, then rerun with `--apply`. The helper archives
the three plists before unloading them with launchctl bootout.

After one week cloud-only:

- rotate credentials that previously lived in the launchd env file;
- retain the archived plists until rollback is no longer needed;
- leave `scripts/install_launchd.py` as legacy/rollback-only.

## Rollback

Pause the cloud schedulers, then restore archived launchd plists:

```bash
python3 /Users/olliepage/Developer/Auto-Procurer/scripts/cutover_launchd.py rollback
```

Review the dry-run output first, then rerun with `--apply`. Because stores,
watcher dedup state, and budget ledger state are blob-synced, the active runner
should continue from the latest uploaded state.
