# [Plan] Refresh README from current runtime

**Status:** plan — implementation lands on this same branch per the fleet dispatch protocol
**Source:** 2026-06-12 fleet audit (operator-held)
**Wave:** 1
**Type:** docs-only planning artifact

## Context

The 2026-06-12 fleet audit found the README "stale and scaffold-biased": it still
reads like a just-generated worker while the repo is materially beyond scaffold.
Verified against `origin/main` (`354fd63`, post-PR #14/#15) on 2026-06-12:

- README's intro says the worker is "born with … one example capability, a pulse
  stub, and a Doctor stub". In fact `src/xsource/cli/cockpit.py::register_all`
  registers 13+ capabilities across shelves A/B/C/D/E/G (new request, trigger,
  reorder, outreach, follow-up, sync, watcher status, black book, publish,
  partner lead, doctor), and the Doctor screen runs real config/auth probes.
- The Quick start comment says `XSOURCE_EMIT_SIGNALS=1 … # -> emitted 0 (no
  horizon yet)`. In fact `src/xsource/signals/build.py` composes four real
  builders (`build_chase_quote_signals`, `build_recurring_service_signals`,
  `build_watcher_health_signals`, `build_store_offline_signals`) into
  `scan_xsource_horizon`; a zero count reflects live data, not missing code.
- The "Make it real" section instructs the next agent to replace the
  signals stub, the example capability, the pulse stub, and the Doctor probes —
  all of which are already implemented. Following it would duplicate or
  overwrite shipped P1–P4 work.
- The Runtime section *was* refreshed by the Cloud Run migration plan (PR #15)
  and is broadly accurate — it must be preserved, not rewritten from scratch.
- README never mentions the cockpit's agent mode (`--agent-stdio`,
  `--allow-apply`), the `request trigger/followup/reorder` commands added in
  PR #14, or the config/credential expectations that Doctor checks.

## Goal

Rewrite README so a new agent or operator reading only the README gets an
accurate picture of the built runtime: CLI surface, cockpit, watcher, signals,
sheet sync, outreach posture, Cloud Run runtime, config expectations, and test
commands. Remove every scaffold instruction that contradicts current code.

## Non-goals

- No code, test, or CI changes.
- No changes to `docs/runbooks/cloud-run-cutover.md` or existing plan docs.
- Not a full operator manual — deep journey detail belongs to the cockpit
  journey map plan (separate branch); cockpit CLI-parity detail belongs to the
  equivalent_cli mappings plan (separate branch). Link to both once merged
  rather than duplicating.
- No new capabilities, no renamed commands.

## Deliverables

### Phase 1 — audit the current README against the code

- [x] Diff every README claim against `uv run xsource --help` (and each
      sub-app's `--help`) plus `src/xsource/cli/__init__.py` registrations.
- [x] List the claims to delete (scaffold "born with" framing, "no horizon
      yet", the whole "Make it real" section) and the claims to keep
      (Runtime/Cloud Run section, CI gates, copier note if still applicable —
      verify `copier update` is still supported before keeping it).
      **Note:** no `.copier-answers.yml` found — `copier update` not supported;
      section removed.

### Phase 2 — rewrite

- [x] New structure: what the worker does (one paragraph) → CLI surface
      (`signals`, `watcher`, `request` with all five request subcommands) →
      cockpit (TTY + `--agent-stdio` agent mode, shelves A–E and G, write-gate /
      draft-never-send posture) → signals (the four horizon builders, the
      `XSOURCE_EMIT_SIGNALS` flag, what "emitted 0" means) → Runtime (keep the
      existing Cloud Run section) → configuration (env vars / token-file
      conventions the Doctor probes check, and what happens when each is
      absent — offline cache fallback, preflight blocks) → development
      (`uv sync`, `uv run pytest -q`, `uv run ruff check .`).
- [x] Quick start commands must be copy-pasteable and match real behaviour,
      including expected output lines for the flag-off and flag-on
      `signals scan` runs.
- [x] Note explicitly that cockpit walks are gated: agent mode is dry-run by
      default and applying requires the `--allow-apply` handshake.

### Phase 3 — consistency sweep

- [x] Update the stale module docstring in `tests/test_signals_build.py` (it
      still describes the horizon as an xfail-guarded stub) **only if** the
      change stays docs/docstring-only; otherwise record it as a follow-up in
      this doc. **Done:** docstring updated; no test logic changed.
- [x] Confirm no README statement contradicts `CLAUDE.md` (agent-navigability
      rules) or the Cloud Run runbook.

## Acceptance criteria

- README contains no claim that the worker is scaffold-only, no "example
  capability / pulse stub / Doctor stub" wording, no "no horizon yet", and no
  "Make it real" instructions to fill already-implemented stubs.
- Every command shown in README exists: each fenced command line, run with
  `--help`, exits 0.
- The five `request` subcommands (`sync`, `sync-all`, `trigger`, `followup`,
  `reorder`) and both `watcher` subcommands (`run`, `status`) are mentioned.
- The Cloud Run Runtime section content from PR #15 is retained (edited for
  flow at most, not removed).
- The configuration section names every env var the Doctor probes check, and
  states the behaviour when each is missing.
- No internal hostnames, personal names, email addresses, or machine-local
  filesystem paths appear in the README.

## Verification

```bash
# every documented command parses
uv run xsource --help
uv run xsource request --help        # shows: sync, sync-all, trigger, followup, reorder
uv run xsource watcher --help        # shows: run, status
uv run xsource signals scan          # "signals: disabled (set XSOURCE_EMIT_SIGNALS=1 to enable)"

# stale wording is gone
grep -nE "Make it real|no horizon yet|example capability|Doctor stub" README.md  # no matches

# docs-only diff
git diff --stat origin/main          # touches README.md (and at most one test docstring)

# repo gates stay green
uv run ruff check . && uv run pytest -q
```

## HANDOFF NOTES

**Phase:** COMPLETE — all three phases implemented, local gates green.

**Decisions taken:**
- `copier update` section removed: no `.copier-answers.yml` in repo, template pull not supported.
- Test docstring in `tests/test_signals_build.py` updated (docs-only, no test logic changed).
- Cloud Run Runtime section preserved verbatim from PR #15 (no edits needed for flow).

**Known-failing tests:** none — 205 passed.

**Next step:** none; PR ready for QA.
