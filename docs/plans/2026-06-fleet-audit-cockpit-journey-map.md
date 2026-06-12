# [Plan] Procurement cockpit journey map

**Status:** plan — implementation lands on this same branch per the fleet dispatch protocol
**Source:** 2026-06-12 fleet audit (operator-held)
**Wave:** 1
**Type:** docs-only planning artifact

## Context

The 2026-06-12 fleet audit drove the cockpit over `--agent-stdio` and found the
operator surface does not distinguish implemented, config-gated, and
placeholder capabilities. Re-verified against `origin/main` (`354fd63`):
`register_all` in `src/xsource/cli/cockpit.py` registers five real walk
handlers (new request, trigger, reorder, outreach, follow-up) alongside eight
`run=None` entries (`request.list`, `request.sync`, `book.search`,
`book.import`, `book.publish`, `watcher.status`, `partner.checkatrade`,
`doctor`) that render a static card even where a real read path exists
(`xsource watcher status` works; the Reply watcher card still shows summary
text only). Real `src/xsource/book/*` modules and `tests/book/*` exist behind
the black-book cards. The audit also observed that inside a shelf menu the
global shelf keys are ignored until back/quit, while help promises shelf keys
open shelves — structured but surprising. Shelves are A/B/C/D/E/G; there is no
F. `request sync-all` has no read-only preview, so it cannot be inspected
safely before mutation.

## Goal

One journey-map document an operator or agent can trust: for each cockpit
journey, what works today, what is config-gated, what is placeholder, and the
target live path — plus the small cleanup pass that makes card status visible
in the cockpit itself instead of only in the doc.

## Non-goals

- Not implementing the black-book / publish / partner capabilities, a
  `request list` data view, or a `book` CLI — those get scoped as follow-ups
  by this map, not built here.
- Not changing the `equivalent_cli` strings (separate plan branch:
  fix stale cockpit equivalent_cli mappings).
- Not changing the framework's modal menu behaviour; this plan documents it
  and, at most, files the framework follow-up.

## Deliverables

### Phase 1 — journey map doc (`docs/cockpit-journeys.md`)

One section per journey, each with: entry point (shelf key + capability key),
current state (implemented / config-gated / placeholder, with the code path),
preconditions (env vars, tokens, open-request state), mutation risk and gate,
and target live path.

- [ ] **New request** (shelf A: `request.new`, `request.trigger`,
      `request.reorder`) — implemented walks; preflight blocks without Maps
      key, LLM key, Sheets token, home postcode; apply creates one Sheet +
      store records behind the apply gate.
- [ ] **Requests** (shelf B: `request.list` placeholder card,
      `request.sync` card → real `xsource request sync` / `sync-all`) —
      target: list renders live store data; sync-all gains a read-only
      preview (`--dry-run`) so operators can inspect before mutating.
- [ ] **Black book** (shelf C: `book.search`, `book.import` placeholder
      cards over real `src/xsource/book/*` modules) — target: cards wired to
      the existing search/import code, read paths first.
- [ ] **Publish** (shelf D: `book.publish`, `partner.checkatrade`
      placeholders) — target: publish wired to the existing publish module;
      checkatrade stays build-only behind the gate.
- [ ] **Outreach** (shelf E: `request.outreach`, `request.followup` walks
      implemented and draft-only; `watcher.status` card) — target: status
      card renders the real watcher data the CLI already prints, including
      the pending-replies backlog.
- [ ] **Diagnostics** (shelf G / `g`: doctor screen implemented with real
      probes; doctor card is `run=None`) — target: one read-only health
      surface combining store counts, watcher status, signal count, and
      config readiness.
- [ ] Document the modal shelf-menu behaviour (global shelf keys inactive
      inside a menu) and that shelves run A–E and G with no F.

### Phase 2 — affordance status cleanup (small, code)

- [ ] Every `run=None` capability's summary states its status explicitly
      (e.g. trailing "Planned — not yet wired." or "Read-only view via CLI."),
      so a rendered card is self-describing instead of looking clickable.
- [ ] Add/extend a drive test asserting each placeholder card's frame carries
      the status wording, and that the two cards with live CLI twins
      (`request.sync`, `watcher.status`) reference commands that parse.

### Phase 3 — follow-up scoping

- [ ] Close the doc with a scoped follow-up table (one row per unbuilt target
      live path: request list data view, sync-all dry-run, book wiring,
      publish wiring, combined status surface) sized roughly and ordered, so
      later implementation PRs can be cut straight from rows.

## Acceptance criteria

- `docs/cockpit-journeys.md` exists and covers all six journeys; every
  capability key in `register_all` appears in exactly one journey section.
- Each journey states implemented vs config-gated vs placeholder, and no
  statement contradicts the code (spot-check: capability keys, shelf letters,
  and command names in the doc all resolve against `src/xsource/cli/`).
- No placeholder card renders without explicit status wording in its summary.
- Drive-based test (not text scraping, per `CLAUDE.md`) covers the placeholder
  cards' status wording; `uv run pytest -q` and `uv run ruff check .` pass.
- No internal hostnames, personal names, email addresses, or machine-local
  filesystem paths appear in the doc.

## Verification

```bash
# doc exists and covers every registered capability key
for k in request.new request.trigger request.reorder request.list request.sync \
         book.search book.import book.publish request.outreach request.followup \
         watcher.status partner.checkatrade doctor; do
  grep -q "$k" docs/cockpit-journeys.md || echo "MISSING $k"
done   # no output

# placeholder cards self-describe (inspect frames via the structured client,
# e.g. drive to shelf B card 1 and assert the status wording in the card frame)
uv run pytest tests/ -k "cockpit or contract" -q

# gates
uv run pytest -q && uv run ruff check .
```
