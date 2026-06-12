# [Plan] Fix stale cockpit equivalent_cli mappings

**Status:** plan — implementation lands on this same branch per the fleet dispatch protocol
**Source:** 2026-06-12 fleet audit (operator-held)
**Wave:** 1
**Type:** docs-only planning artifact

## Context

The 2026-06-12 fleet audit found cockpit frames advertising `equivalent_cli`
commands that do not exist, so an operator following a structured frame's
"equivalent CLI" hint gets `No such command`. Much of this was already fixed by
the P4 completion work (merged PR #14: `request trigger/followup/reorder` are
now real Typer commands, and the placeholder cards plus the `request.new` /
`request.outreach` *capability registrations* were switched to
`equivalent_cli=None`). Re-verified against `origin/main` (`354fd63`) on
2026-06-12, the stale strings that REMAIN are all at the walk/confirm layer of
`src/xsource/cli/cockpit.py`, which still leaks into preflight and apply
frames:

| Location (cockpit.py) | String | Reality |
|---|---|---|
| `_review_apply_step` → `confirm_apply(...)` (~line 291) | `xsource request new` | `uv run xsource request new --help` → exit 2, no such command |
| `_request_new_handler = make_walk_handler(...)` (~line 335) | `xsource request new` | same |
| `_outreach_apply_step` → `confirm_apply(...)` (~line 351) | `xsource request outreach` | `uv run xsource request outreach --help` → exit 2, no such command |
| `_request_outreach_handler = make_walk_handler(...)` (~line 389) | `xsource request outreach` | same |
| `doctor_unconfigured_renderable()` (~line 1057) | note titled `xsource doctor` | no `doctor` CLI command exists |

Real `request` subcommands on main: `sync`, `sync-all`, `trigger`, `followup`,
`reorder` (`src/xsource/cli/request.py`).

## Goal

No frame the cockpit can emit — capability card, walk preflight, walk step, or
apply confirmation — names a CLI command that does not parse. Adopt one parity
policy and enforce it with a test so the gap cannot reopen.

## Non-goals

- Not implementing `xsource request new` or `xsource request outreach` as CLI
  commands. The P4 round already chose "no fictional CLI" over inventing
  commands; these two walks are interactive wizards whose CLI twins, if ever
  wanted, are their own feature work. If the implementer disagrees, that is a
  policy escalation to record in this doc, not a silent scope change.
- Not wiring the placeholder cards' `run=None` actions (covered by the cockpit
  journey map plan on its own branch).
- No changes to the framework dependency; only this repo's cockpit module and
  tests.

## Deliverables

### Phase 1 — fix the five stale strings

- [ ] `_request_new_handler` and its `confirm_apply` call: replace
      `equivalent_cli="xsource request new"` with `None` (cockpit-only walk).
      If the walk-handler signature requires a value, pass `None` the same way
      the capability registrations do.
- [ ] `_request_outreach_handler` and its `confirm_apply` call: same treatment
      for `xsource request outreach`.
- [ ] `doctor_unconfigured_renderable`: retitle the note so it does not read as
      a runnable command (e.g. "Doctor" rather than "xsource doctor").

### Phase 2 — enforce parity so it cannot regress

- [ ] Add a test that collects every `equivalent_cli` string reachable from the
      cockpit (registered capabilities AND walk handlers / confirm-apply
      prompts) and asserts each one, invoked with `--help` against the Typer
      app, exits 0. Implementation hint: walk the registered `CapabilitySpec`s
      and the module-level walk handlers, or grep-assert as a fallback if
      runtime introspection is impractical — but a runtime check is preferred.
- [ ] Extend the agent-stdio drive test path (per `CLAUDE.md`: drive, don't
      scrape) to open the New request and Draft outreach walks to preflight and
      assert their frames carry no nonexistent command string.

### Phase 3 — document the policy

- [ ] Add a short "CLI parity policy" note in this doc (or the journey-map doc
      if it merges first, with a cross-link): every `equivalent_cli` must name
      a parseable command; cockpit-only flows use `None`; new walks must ship
      either a real CLI twin or `None`, never an aspirational string.

## Acceptance criteria

- `git grep -n '"xsource request new"' src/` and
  `git grep -n '"xsource request outreach"' src/` return no matches.
- `git grep -nE 'equivalent_cli="xsource' src/` returns only strings that
  parse: each match, run as `uv run <string> --help`, exits 0.
- The new parity test fails if a fictional `equivalent_cli` is reintroduced
  (demonstrate once by temporarily restoring a stale string locally).
- Cockpit behaviour is otherwise unchanged: walks still open, preflight still
  reports readiness, apply gates still require the handshake.
- `uv run pytest -q` and `uv run ruff check .` pass.

## Verification

```bash
# stale strings gone
git grep -n '"xsource request new"' src/        # no output
git grep -n '"xsource request outreach"' src/   # no output

# every remaining mapping parses
git grep -hoE 'equivalent_cli="[^"]+"' src/ | sed 's/equivalent_cli=//;s/"//g' | sort -u
# for each line above:
uv run <command> --help   # exit 0

# real commands unchanged
uv run xsource request --help   # sync, sync-all, trigger, followup, reorder

# gates
uv run pytest -q && uv run ruff check .
```
