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

- [x] `_request_new_handler` and its `confirm_apply` call: replaced stale strings.
      `confirm_apply` gates use `None` (interactive path ignores the value; agent
      path serialises to JSON null). `make_walk_handler` uses `""` — framework's
      `chip()` cannot render `None` without crashing (`None.strip()` raises); an
      empty string renders a blank chip and doesn't crash. See deviation note below.
- [x] `_request_outreach_handler` and its `confirm_apply` call: same treatment.
- [x] `doctor_unconfigured_renderable`: title changed from `"xsource doctor"` to
      `"Doctor"`.

### Phase 2 — enforce parity so it cannot regress

- [x] `tests/cli/test_equivalent_cli_parity.py` — `test_equivalent_cli_parses`:
      collects non-None/non-empty `equivalent_cli` strings from the capability
      registry and asserts each, with `--help` via Typer's `CliRunner`, exits 0.
      Five commands verified: `request trigger`, `request followup`,
      `request reorder`, `request sync`, `watcher status`.
- [x] `test_cockpit_only_walk_preflight_carries_no_fictional_cli`: drives
      `request.new` and `request.outreach` in agent mode via `shell._open_capability`
      + a `q`-returning read_key, captures the `walk.preflight` frame, and asserts
      `equivalent_cli` is not in the set of known fictional commands.

### Phase 3 — document the policy

- [x] CLI parity policy (below) added to this doc.

---

## CLI parity policy

Every `equivalent_cli` in this worker MUST name a command that parses (exits 0 with
`--help` against the Typer `app`). Enforced by `tests/cli/test_equivalent_cli_parity.py`.

| Walk / capability class | `equivalent_cli` rule |
|---|---|
| Has a real Typer command | Use the full command string (e.g. `"xsource request trigger"`) |
| Cockpit-only — no CLI twin | Use `None` for `CapabilitySpec`; use `""` for `make_walk_handler` and `confirm_apply` (framework's `chip()` crashes on `None`) |
| New walk being added | Ship either a real CLI twin or use `None`/`""` — never an aspirational string |

**Why `""` and not `None` for `make_walk_handler`**: the clonway-cockpit framework's
`chip(cli)` calls `cli.strip()` unconditionally in `render_preflight`. Until the
framework adds a `None`-guard, cockpit-only walk handlers must use `""` to avoid a
crash in the preflight render. The `CapabilitySpec` (capability card) correctly uses
`None` with `# type: ignore[arg-type]` because `render_capability_card` is never called
for specs with a `run` handler set.

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

## Deviations from plan

- **`make_walk_handler(equivalent_cli="")` not `None`**: The plan said to use `None`
  for walk handlers the same way capability registrations do. However, the framework's
  `render_preflight` calls `chip(equivalent_cli)` unconditionally, and `chip(None)`
  raises `AttributeError: 'NoneType' has no attribute 'strip'`. The walk crashes with a
  walk-result error frame instead of showing the preflight. Used `""` instead, which
  renders a blank chip (cosmetically fine) and doesn't crash. The `confirm_apply` gates
  correctly use `None` since the interactive path never reads `equivalent_cli`.
- **No framework change**: The plan's non-goal of "no framework changes" was preserved.
  If the framework adds a `None`-guard in `chip`, the `""` can be revisited.

## HANDOFF NOTES

**Status**: COMPLETE. All three phases implemented and verified.

**What was done**:
- Phase 1: 5 stale strings fixed in `src/xsource/cli/cockpit.py`
- Phase 2: `tests/cli/test_equivalent_cli_parity.py` added (7 tests all green)
- Phase 3: CLI parity policy documented in this file

**Gates**: `uv run pytest -q` → 212 passed. `uv run ruff check .` → clean.

**Next**: No follow-up needed. If `make_walk_handler` ever needs `None` (not `""`),
open a framework PR to clonway-cockpit to guard `chip(cli)` against `None`.
