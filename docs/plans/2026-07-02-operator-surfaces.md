# [Plan] Operator surfaces: wire request.list + black-book walks/CLI (kill the run=None shelves)

- **Date:** 2026-07-02 · **Branch:** `claude/plan-operator-surfaces` · **Status:** plan — implementation lands on this same branch per the fleet dispatch protocol
- **Type:** docs-only planning artifact (this file is the binding spec + implementation plan)
- **Related:** `docs/cockpit-journeys.md` follow-up rows 1, 4, 5, 6 · `docs/plans/2026-06-fleet-audit-cockpit-journey-map.md`

> **For agentic workers:** REQUIRED SUB-SKILL: implement this plan task-by-task (Claude: `superpowers:subagent-driven-development` or `superpowers:executing-plans`; Codex: same phase/TDD/verification discipline). Steps use checkbox (`- [ ]`) syntax for tracking. Tick checkboxes as work lands and commit this plan with the code. Keep `## HANDOFF NOTES` current.

## Context (current-state evidence, verified against `origin/main` @ `db5fbc8`)

`register_all()` in `src/xsource/cli/cockpit.py` (~L947–1007) still registers four
capabilities with `run=None` and summary "Planned — not yet wired.":

- `request.list` (shelf B, item 2)
- `book.search` (shelf C, item 1)
- `book.import` (shelf C, item 2)
- `book.publish` (shelf D, item 1)

Meanwhile the domain code behind them **exists and is tested**:

- `src/xsource/book/search.py` — `search_suppliers()` (tested in `tests/book/test_search.py`)
- `src/xsource/book/importer.py` — `import_csv()` with name-dedupe (tested in `tests/book/test_importer.py`)
- `src/xsource/book/publish.py` — `build_directory_values()` (tested in `tests/book/test_publish.py`)
- `src/xsource/store/jsonl.py` — corrupt-line quarantine on load (`<file>.quarantine`)

There is **no** `xsource book` CLI group and **no** `xsource request list` command
(`src/xsource/cli/__init__.py` registers signals/watcher/request/invoice only). The
parity gate `tests/cli/test_equivalent_cli_parity.py` enforces that every non-empty
`equivalent_cli` in the registry parses (`--help` exit 0) — so new walks need matching
CLI commands, not fictional strings (the PR #17 failure class).
`tests/test_cockpit_placeholders.py` pins "Planned — not yet wired." wording for
exactly these four keys and will fail the moment they gain `run=` handlers — it must
be updated in the same task that wires each walk.

Baseline gates on `origin/main`: `uv run pytest -q` → **286 passed**.

## Goal

The four dead shelves become real, gated operator surfaces: each gets a cockpit walk
wired at its **existing shelf position** plus a matching CLI command, with read paths
never writing, writes strictly behind `confirm_apply`, and every new walk × state
covered by a test pinned to a fixture in this plan.

## Non-goals

- `partner.checkatrade` post gate (stays build-only placeholder; shelf D item 2 unchanged).
- New acquisition channels of any kind.
- `request.sync` cockpit walk / `sync-all --dry-run` (journey-map follow-up row 3) and
  `watcher.status` card wiring (row 2) and doctor probe extension (row 7) — out of scope.
- Fixing the framework `chip()` crash for `equivalent_cli=None` cards (clonway-cockpit issue;
  after this PR the four keys carry real CLI strings so the crash no longer applies to them).
- README doc-truth fixes unrelated to these surfaces (invoice CLI lines, horizon-builder count,
  pre-commit claim) — owned by the separate doc-truth plan PR. **This PR only adds README lines
  for the commands it itself introduces.**

## Binding decisions (do not re-litigate)

1. **Shelf positions do not move.** Registration order in `register_all()` is the shelf-item
   order the drive tests already script (`tests/test_cockpit_placeholders.py` drives B→3, E→3).
   The four placeholder tuples are replaced by full registrations **at the same loop positions**;
   a new order-pinning test is the validator (see HR6 table).
2. **One CLI string per capability, defined once.** Module constants in
   `src/xsource/cli/cockpit.py` are the single source for each `equivalent_cli`, used by BOTH
   the `CapabilitySpec` and the walk handler/`confirm_apply`:
   `_CLI_REQUEST_LIST = "xsource request list"`, `_CLI_BOOK_SEARCH = "xsource book search"`,
   `_CLI_BOOK_IMPORT = "xsource book import"`, `_CLI_BOOK_PUBLISH = "xsource book publish"`.
3. **Row formats are defined once.** `format_request_row()` lives in `src/xsource/cli/request.py`;
   `format_supplier_row()` lives in `src/xsource/book/search.py`. CLI commands and walk steps both
   call them — no second f-string per surface.
4. **Import preview and import write share one parser.** `import_csv()` gains
   `dry_run: bool = False`; `dry_run=True` computes the identical `{"imported": N, "skipped": M}`
   report without calling `store.upsert()`. No separate preview parser that can drift.
5. **Publish regenerates ONE directory sheet in place.** The sheet id is persisted in
   `directory-sheet.json` (worker state dir, GCS-synced via the existing `SyncedFile` +
   `state_blob` pattern from `Budget` / `wiring.py`). Re-publish updates the same sheet; a
   deleted sheet (`404`) is recreated and the state overwritten.
6. **The staff directory is shared read-only** (`role="reader"`), unlike request sheets
   (`role="writer"`). Directory values are written with `valueInputOption="RAW"` so a cell that
   begins with `=` can never execute as a formula (formula-injection guard; request sheets keep
   their existing `USER_ENTERED` behaviour untouched).
7. **Quarantine visibility reports the current load, not the cumulative file.**
   `JsonlStore` counts lines quarantined during *this* `_load()` (`.quarantined`), because the
   quarantine file grows by append on every reload of a store whose `.jsonl` still holds the
   corrupt line — a cumulative count would be nondeterministic across cockpit screens.
8. **`money_movement=False` for all four capabilities** — nothing here moves money or changes a
   payment destination; import/publish write reversible records/artifacts only.

## Functional contract

### New CLI commands (exact output; all exit 0 unless stated)

**`xsource request list`** (`src/xsource/cli/request.py`) — read-only. One row per request in
the store, sorted by `id` ascending, each `format_request_row(r)`:
`f"{r.id}\t{r.status}\t{r.created_at}\t{need}"` where `need = " ".join(r.raw_need.split())`
(whitespace-collapsed so a multi-line need cannot break the row shape). Empty store → prints
nothing, exit 0. When `requests_.quarantined > 0`, first prints to **stderr**:
`warning: {n} corrupt line(s) quarantined in {requests_.path.name}`.

**`xsource book search TERM`** (new `src/xsource/cli/book.py`) — read-only. One row per
`search_suppliers(suppliers.all(), term)` match, each `format_supplier_row(s)`:
`f"{s.id}\t{s.name}\t{','.join(s.categories)}\t{','.join(s.tags)}\t{s.phone or ''}"`.
No matches / empty book → prints nothing, exit 0. Same stderr quarantine warning as above
(suppliers store).

**`xsource book import CSV_PATH [--dry-run]`** — nonexistent path → `typer.BadParameter`
(exit 2). Otherwise calls `import_csv(csv_path, suppliers, today=<ISO today>, dry_run=<flag>)`
and echoes the report dict verbatim, e.g. `{'imported': 1, 'skipped': 1}`. With `--dry-run`
nothing is written. `StoreOffline` (no GCS bucket / offline cache) → stderr
`store offline: {exc}`, exit 1.

**`xsource book publish`** — empty book → stderr `no suppliers to publish`, exit 1, no API
calls. Otherwise runs the publish flow (below) and echoes the report dict, e.g.
`{'sheet_id': 'SID-1', 'sheet_url': 'https://…', 'rows': 2, 'created': True}`.

`book_app` is registered in `src/xsource/cli/__init__.py` via `app.add_typer(book_app, name="book")`.

### New cockpit walks (all in `src/xsource/cli/cockpit.py`, house `make_walk_handler` style)

| key | shelf/pos | steps (`total=`) | preconditions fn | gate |
|---|---|---|---|---|
| `request.list` | B/2 | List (`total=2`) | `_readonly_preconditions` | none — read-only |
| `book.search` | C/1 | Term → Results (`total=3`) | `_readonly_preconditions` | none — read-only |
| `book.import` | C/2 | File → Preview → Apply (`total=4`) | `_book_write_preconditions` | `confirm_apply(prompt="Import suppliers from CSV?", equivalent_cli=_CLI_BOOK_IMPORT)` |
| `book.publish` | D/1 | Preview → Publish (`total=3`) | `_publish_preconditions` | `confirm_apply(prompt="Publish staff directory?", equivalent_cli=_CLI_BOOK_PUBLISH)` |

- `_readonly_preconditions`: single row `Store loaded` — ok when `build_stores()` produced all
  three stores (offline read-only cache **still passes**; detail says `GCS store available` or
  `offline read-only cache`; only a construction failure blocks with `store unavailable`).
- `_book_write_preconditions`: `Store reachable` — requires `_store_online(...)` (an offline
  store cannot accept `upsert`, so the write walk blocks at preflight).
- `_publish_preconditions`: `Sheets token` (env path set + file exists), `Store reachable`
  (online), `Suppliers available` (`{n} supplier(s)` / `none`).
- Walk result messages (`walk.result` frame `meta["message"]`, pinned):
  - request.list: `f"{open_n} open · {total_n} total{_quarantine_suffix(requests_)}"`
  - book.search: `f"{len(matches)} match(es) for '{term}'{_quarantine_suffix(suppliers)}"`
  - book.import: `f"Imported {report['imported']}, skipped {report['skipped']}."`
  - book.publish: `f"Published directory ({report['rows']} supplier(s))."` with
    `result_links=[("Directory", sheet_url)]`
  - `_quarantine_suffix(store)` returns `f" · quarantined: {n} corrupt line(s)"` when
    `store.quarantined > 0`, else `""` — one helper, used by both read walks.
- Registered summaries (replace "Planned — not yet wired."):
  - `request.list`: `"List procurement requests from the store. Read-only."`
  - `book.search`: `"Search saved suppliers by name, category, or tag. Read-only."`
  - `book.import`: `"Seed the supplier store from CSV behind the apply gate."`
  - `book.publish`: `"Regenerate the read-only staff supplier directory behind the apply gate."`
- Blast radii (new module constants, house style): import writes supplier records only
  (reversible by id; re-import skips existing names); publish creates/updates ONE directory
  sheet + one state file (reversible: delete sheet / remove state file); list/search read-only
  ("Writes nothing.").
- No new `render_*`/`model_*` functions are added — walks render through framework screens, so
  `tests/test_cockpit_contract.py::test_render_model_parity` stays green by construction, and
  `test_cockpit_drives_clean` continues to pass (acceptance row below re-runs both).

### Publish flow (new code)

`src/xsource/book/publish.py` gains:

- `DIRECTORY_TITLE = "Supplier directory"` (single source for CLI + walk).
- `class DirectorySheetGone(RuntimeError)`.
- `load_directory_state(state_file) -> dict` / `save_directory_state(state_file, sheet_id, sheet_url)`
  — JSON `{"sheet_id": …, "sheet_url": …}` at `Path(cfg.state_dir) / "directory-sheet.json"`,
  hydrated/uploaded through `SyncedFile` (`xsource.store.files`), blob from
  `state_blob(cfg, "directory-sheet.json")`. Malformed/missing state file reads as `{}` (never raises).
- `publish_directory(suppliers, *, state_file, client, title, folder_id, share_with) -> dict`:
  raises `ValueError` on empty supplier list; builds values via the existing
  `build_directory_values()` (unchanged — it stays the single source of the 8 directory columns);
  update-in-place when state has a `sheet_id`, falling back to create on `DirectorySheetGone`;
  returns `{"sheet_id", "sheet_url", "rows": len(values) - 1, "created": bool}`.

`src/xsource/sheet/client.py` gains two methods (same thin-wrapper style as
`create_request_sheet`, which stays untouched):

- `create_directory_sheet(title, values, folder_id, share_with) -> (sheet_id, sheet_url)`:
  `spreadsheets().create` → `values().update(range="A1", valueInputOption="RAW")` → optional
  Drive `addParents` → optional `permissions.create(type="group", role="reader",
  sendNotificationEmail=False)`.
- `update_directory_sheet(sheet_id, values) -> None`: `values().update(range="A1",
  valueInputOption="RAW")` then `values().clear(range=f"A{len(values) + 1}:H")` (clears stale
  trailing rows; `H` = last of the 8 directory columns). An `HttpError` with HTTP status 404
  raises `DirectorySheetGone(sheet_id)`; other errors propagate.

`src/xsource/wiring.py` gains `build_directory_state_file(cfg) -> SyncedFile` (single source of
the state path/blob for CLI + walk).

### Store quarantine surface (new code)

`src/xsource/store/jsonl.py`: `JsonlStore` gains `self.quarantined: int = 0`, incremented once
per corrupt line skipped in `_load()`. `src/xsource/store/remote.py`: `SyncedStore` gains a
`quarantined` property delegating to the inner store. No behaviour change to quarantine
file writing.

## Safety invariants (HR3 — each cell bound to a test; all tests new unless noted)

| # | state | required behaviour | test |
|---|---|---|---|
| 1 | `book.import` gate declined | `import_csv` never called with `dry_run=False`; store file unchanged; step returns `ok=False`, message `"Apply declined."` | `test_book_import_declined_writes_nothing` |
| 2 | `book.import` CSV row name already in store (case-insensitive) | row skipped; no duplicate supplier | existing `tests/book/test_importer.py::test_reimport_skips_existing_by_name` + walk-level `test_book_import_apply_skips_existing` |
| 3 | `book.import` re-run with the same CSV | report `{"imported": 0, "skipped": N}`; store contents identical before/after | `test_book_import_rerun_is_noop` |
| 4 | `book.import` walk, store offline | preflight `Store reachable` row red → walk never reaches the gate | `test_book_import_preflight_blocks_offline` |
| 5 | `book.import --dry-run` (CLI) and Preview step (walk) | same report as a real run would give; zero `upsert` calls | `test_import_dry_run_writes_nothing` |
| 6 | `book.publish` gate declined | zero Sheets/Drive calls; no state write; `ok=False`, `"Apply declined."` | `test_book_publish_declined_writes_nothing` |
| 7 | `book.publish`, state holds `sheet_id` | `update_directory_sheet` called; `create_directory_sheet` NOT called; `created=False` | `test_publish_updates_existing_sheet` |
| 8 | `book.publish`, saved sheet deleted (client raises `DirectorySheetGone`) | falls back to create; state overwritten with the new id; `created=True` | `test_publish_recreates_when_gone` |
| 9 | `book.publish`, empty black book | CLI exits 1 before any API call; walk Preview step fails `"No suppliers in the black book."` before the gate | `test_publish_empty_book_blocks` (flow) + `test_book_publish_cli_empty_book` |
| 10 | `book.publish` share | permission body is exactly `{"type": "group", "role": "reader", …}` — never `writer` | `test_directory_sheet_shared_read_only` |
| 11 | `book.publish` values write | `valueInputOption == "RAW"` on both create and update paths | `test_directory_values_written_raw` |
| 12 | `request.list` / `book.search` (any state) | zero `upsert` calls on any store — read paths cannot write | `test_readonly_walks_never_upsert` |
| 13 | corrupt line in a store file | record skipped + quarantined; list/search still succeed and surface the count | `test_search_walk_surfaces_quarantine` |
| 14 | agent mode (`--agent-stdio`, no `--allow-apply`) on import/publish | framework `confirm_apply` dry-run declines → same "declined" cells as #1/#6 (framework-enforced; declined-path tests #1/#6 prove the walk honours a False gate) | covered by #1/#6 + framework contract |

**Writes named per HR4** (no money moves; no allocation arithmetic applies — stated so QA
doesn't have to ask):

- `book.import` — **idempotency key:** casefolded supplier `name` (the dedupe in `import_csv`);
  re-import of any prefix of a previous run skips already-imported rows. **Partial failure:**
  offline/crash after K upserts leaves K rows imported (each `upsert` is atomic:
  tempfile + `os.replace`, then blob upload); recovery = re-run the same import, which skips
  those K by name and imports the rest (cell #3 is the proof).
- `book.publish` — **idempotency key:** the persisted `sheet_id` in `directory-sheet.json`;
  re-publish updates the same artifact instead of minting siblings. **Partial-failure windows:**
  (a) create OK → state save raises → `publish_directory` logs a warning
  (`xsource.book` logger) and still returns the report (the sheet exists and is shared); the
  next publish creates a fresh sheet and the old one is inert — operator deletes it
  (`test_publish_state_save_failure_still_reports`); (b) update OK → `clear` fails → the
  walk step returns `ok=False`, `f"Publish failed: {exc}"`; re-running is safe because
  update + clear are idempotent for the same values (`test_publish_apply_step_reports_api_error`).

## Full state set (HR5 — acceptance checkboxes; each row lands as a test in the named task)

`request.list` (Task 1 CLI, Task 3 walk):
- [ ] empty store → CLI prints nothing (exit 0); walk result `"0 open · 0 total"`
- [ ] mixed open/closed fixture → rows + result pinned in the worked example below
- [ ] corrupt line in `requests.jsonl` → stderr warning (CLI) / `· quarantined: 1 corrupt line(s)` suffix (walk)
- [ ] store offline (local cache) → still lists; precondition detail `offline read-only cache`, not blocked
- [ ] full drive: `CockpitDriver` reaches a `walk.result` frame with the pinned message (`test_request_list_walk_result_via_drive`)

`book.search` (Task 2 CLI, Task 3 walk):
- [ ] empty term → step fails `"No search term entered."`
- [ ] no matches → result `"0 match(es) for 'roofing'"`; CLI prints nothing, exit 0
- [ ] match by name / by category / by tag (three assertions; fixture below)
- [ ] empty book → `"0 match(es) for '<term>'"`
- [ ] corrupt line in `suppliers.jsonl` → quarantine suffix / stderr warning

`book.import` (Task 2 CLI, Task 5 walk):
- [ ] nonexistent path → CLI exit 2; walk File step fails `f"No such file: {path}"`
- [ ] header-only CSV → `{'imported': 0, 'skipped': 0}`
- [ ] duplicate against store + intra-CSV duplicate row → both counted in `skipped`
- [ ] `--dry-run` / Preview → report identical to wet run, zero writes
- [ ] gate declined / gate accepted (invariant cells #1, #3)
- [ ] store offline → CLI exit 1; walk blocked at preflight (cell #4)

`book.publish` (Task 4 flow+CLI, Task 5 walk):
- [ ] empty book (cell #9)
- [ ] first publish → create path, state written, `created: True`
- [ ] re-publish → update path, no create (cell #7)
- [ ] sheet gone → recreate + state overwrite (cell #8)
- [ ] gate declined (cell #6)
- [ ] Sheets token missing → walk blocked at preflight (`Sheets token` red)
- [ ] `share_with` unset (`XSOURCE_STAFF_SHARE_GROUP` absent) → no `permissions.create` call
- [ ] non-404 API error on update → step fails `"Publish failed: …"` (partial-failure (b))

Cross-cutting:
- [ ] every new `equivalent_cli` string parses (`--help` exit 0) — auto-covered by the existing
      parametrized `test_equivalent_cli_parses` the moment the registry carries the strings
- [ ] preflight `equivalent_cli` == registry `equivalent_cli` for all four keys (HR6 validator)
- [ ] shelf item order pinned for shelves A/B/C/D/E (HR6 validator)
- [ ] `tests/test_cockpit_placeholders.py` updated: the four keys leave
      `_PLACEHOLDER_STATUS_MARKERS`; remaining placeholders (`request.sync`, `watcher.status`,
      `partner.checkatrade`, `doctor`) keep their markers and drive tests
- [ ] `test_render_model_parity` and `test_cockpit_drives_clean` still pass unmodified

## One source of truth + validators (HR6)

| value | source of truth | other surfaces | boundary validator |
|---|---|---|---|
| CLI strings (4) | `_CLI_*` constants in `cockpit.py` | `CapabilitySpec.equivalent_cli`, walk handlers, `confirm_apply` | `test_wired_walk_preflight_cli_matches_registry` + existing `test_equivalent_cli_parses` |
| request row format | `format_request_row` (`cli/request.py`) | CLI + walk step | both tests assert the same pinned literal rows |
| supplier row format | `format_supplier_row` (`book/search.py`) | CLI + walk step | same pattern |
| import parse/dedupe | `import_csv(dry_run=…)` | CLI, `--dry-run`, walk Preview, walk Apply | `test_import_dry_run_writes_nothing` asserts dry/wet reports equal |
| directory columns | `_HEAD` in `book/publish.py` via `build_directory_values` | sheet create + update + clear-range end column `H` | existing `tests/book/test_publish.py` pins the 8 columns; `update_directory_sheet` derives clear range from `len(values)`, column end stated as the constant `H` with the comment tying it to `_HEAD` |
| directory state path | `build_directory_state_file` (`wiring.py`) | CLI publish + walk apply | single call site each; grep acceptance below |
| shelf positions | registration order in `register_all()` | shelf menus, placeholder drive tests | `test_shelf_item_order_is_stable` |
| quarantine wording | `_quarantine_suffix` (`cockpit.py`) | list + search walk summaries | one helper; tests pin the suffix through it |

## Worked examples (HR7 — figures computed from the fixtures this plan ships)

**Fixture A (suppliers, used by search/publish tests; synthetic, identifier-free):**

```python
_SUPPLIERS = [
    Supplier(id="s-0001", name="Alpha Tree Care", categories=["trees-grounds"],
             tags=["tree-surgery"], phone="+441632960001"),
    Supplier(id="s-0002", name="Beta Heating", categories=["heating"], tags=["boiler"]),
]
```

- `search_suppliers(_SUPPLIERS, "heating")` → 1 match (`s-0002`: name AND category hit, counted
  once) → walk result `"1 match(es) for 'heating'"`; CLI row exactly
  `s-0002\tBeta Heating\theating\tboiler\t` (no phone → empty last field).
- `search_suppliers(_SUPPLIERS, "roofing")` → 0 → `"0 match(es) for 'roofing'"`.
- `build_directory_values(_SUPPLIERS)` → 1 header + 2 rows = 3 values rows → publish report
  `rows = 3 - 1 = 2` → walk result `"Published directory (2 supplier(s))."`; update-path clear
  range `A4:H` (`len(values) + 1 = 4`).

**Fixture B (CSV, used by import tests; store pre-seeded with `s-0002` "Beta Heating"):**

```python
_CSV = """name,category,tags,phone,email,notes
Gamma Roofing,roofing,slate;flat-roof,01632 960100,gamma@example.com,synthetic seed row
Beta Heating,heating,boiler,01632 960101,,
"""
```

- Wet run: `Gamma Roofing` new → imported, id `s-0003` (`next_id` over existing max `s-0002`);
  `Beta Heating` exists → skipped ⇒ report `{"imported": 1, "skipped": 1}` ⇒ walk result
  `"Imported 1, skipped 1."`
- Re-run: `{"imported": 0, "skipped": 2}`.
- Dry run against the same seeded store: identical `{"imported": 1, "skipped": 1}`, zero writes.

**Fixture C (requests, used by list tests):**

```python
_REQUESTS = [
    Request(id="r-0001", created_at="2026-06-20T10:00:00+00:00", raw_need="fence repair"),
    Request(id="r-0002", created_at="2026-06-01T09:00:00+00:00", raw_need="annual boiler service",
            status="closed"),
]
```

- CLI stdout, exactly two lines, id-sorted:
  ```
  r-0001	open	2026-06-20T10:00:00+00:00	fence repair
  r-0002	closed	2026-06-01T09:00:00+00:00	annual boiler service
  ```
- Walk result: `1` open of `2` total → `"1 open · 2 total"`.

**Fixture D (quarantine):** a `suppliers.jsonl` containing one valid line (the `s-0001` record
from Fixture A as JSON) plus the literal line `not json` → store loads 1 record,
`store.quarantined == 1` → search for `"alpha"` yields
`"1 match(es) for 'alpha' · quarantined: 1 corrupt line(s)"`.

## External contract grounding (HR12)

The Sheets/Drive request/response shapes used here are exactly the ones already exercised in
production by `SheetClient.create_request_sheet` (`src/xsource/sheet/client.py:15-68`):
`spreadsheets().create` returning `spreadsheetId`/`spreadsheetUrl`, `values().update`,
Drive `files().update(addParents=…)`, `permissions().create(type="group", …)`. The two additions
(`values().clear`, `role="reader"`) are documented Sheets v4 / Drive v3 API surface
(`spreadsheets.values.clear`; Drive permission roles include `reader`). A deleted spreadsheet
returns HTTP 404, surfaced by `googleapiclient` as `HttpError` — the 404 detection must accept
both `exc.status_code` (newer clients) and `exc.resp.status` (older), as pinned in the snippet
in Task 4. Test fakes mirror the tuple/report shapes of the existing house fake
(`tests/walks/test_request_new.py::fake_sheet`), not an invented model.

## Global constraints

- Public repo: no real supplier names/ids, hostnames, or emails in docs, fixtures, or examples —
  all new fixtures use the synthetic names above and Ofcom drama-range phone numbers.
- Draft-never-send posture unchanged: nothing in this PR touches Gmail.
- All writes behind `confirm_apply` (framework single write gate); agent mode stays dry-run
  by default.
- **Operator-facing change → RUNBOOK DELTA required (HR1):** new CLI commands + four live
  walks. Task 7 posts it on `hearth-care/auto-orchestrator#196` and repeats it in DONE.
- **Depends on:** nothing unmerged — no wave tag (HR11). Independent of the doc-truth plan PR;
  if both touch the README CLI fence, whichever lands second takes a trivial rebase (this PR
  adds only the four new command lines).
- **Gates (HR2 — the exact commands CI runs, from `.github/workflows/ci.yml`; run from repo
  root, paste output tails in DONE):**
  `uv run pytest -q` · `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy src`
- Tech stack: Python 3.12 stdlib + existing deps only (`typer`, `googleapiclient` already
  present). **No new dependencies.**

---

## Tasks

### Task 1: `xsource request list` + quarantine counters

**Files:** modify `src/xsource/store/jsonl.py`, `src/xsource/store/remote.py`,
`src/xsource/cli/request.py`; test `tests/cli/test_request_list.py` (new),
`tests/store/test_jsonl.py` (extend).

**Production call site (HR9):** `request_app` in `src/xsource/cli/request.py` (already mounted
on the root app in `src/xsource/cli/__init__.py:29`).

- [x] **Step 1 — failing tests** (new file `tests/cli/test_request_list.py`; `_REQUESTS` = Fixture C):

```python
from typer.testing import CliRunner

from xsource.cli import app
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Request

# typer 0.26.x CliRunner: no mix_stderr kwarg; stdout and stderr are captured
# separately by default (result.stdout / result.stderr).
runner = CliRunner()


def _seeded_requests(tmp_path):
    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    store.upsert(Request(id="r-0001", created_at="2026-06-20T10:00:00+00:00",
                         raw_need="fence repair"))
    store.upsert(Request(id="r-0002", created_at="2026-06-01T09:00:00+00:00",
                         raw_need="annual boiler service", status="closed"))
    return store


def test_request_list_prints_pinned_rows(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod
    store = _seeded_requests(tmp_path)
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = runner.invoke(app, ["request", "list"])
    assert result.exit_code == 0
    assert result.stdout == (
        "r-0001\topen\t2026-06-20T10:00:00+00:00\tfence repair\n"
        "r-0002\tclosed\t2026-06-01T09:00:00+00:00\tannual boiler service\n"
    )


def test_request_list_empty_store_prints_nothing(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod
    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = runner.invoke(app, ["request", "list"])
    assert result.exit_code == 0 and result.stdout == ""


def test_request_list_warns_on_quarantine(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod
    path = tmp_path / "requests.jsonl"
    path.write_text(
        '{"id": "r-0001", "created_at": "2026-06-20T10:00:00+00:00", "raw_need": "fence repair"}\n'
        "not json\n"
    )
    store = JsonlStore(path, Request)
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = runner.invoke(app, ["request", "list"])
    assert result.exit_code == 0
    assert "warning: 1 corrupt line(s) quarantined in requests.jsonl" in result.stderr
    assert result.stdout.splitlines() == [
        "r-0001\topen\t2026-06-20T10:00:00+00:00\tfence repair"
    ]
```

  Plus in `tests/store/test_jsonl.py`: `test_quarantined_counts_current_load` — a file with one
  valid + one corrupt line loads with `store.quarantined == 1`; constructing a second store over
  the same (unchanged) file also reports `1`, not `2`.
- [x] **Step 2 — run, confirm RED:** `uv run pytest tests/cli/test_request_list.py tests/store/test_jsonl.py -q`
  → expect `Error: No such command 'list'` (exit 2) assertions failing and
  `AttributeError: 'JsonlStore' object has no attribute 'quarantined'`.
- [x] **Step 3 — implement:** `JsonlStore.__init__` sets `self.quarantined = 0` **before**
  `_load()`; the `except` branch increments it. `SyncedStore` gains
  `@property def quarantined(self) -> int: return self._store.quarantined`. In
  `cli/request.py` add `format_request_row(request) -> str` (whitespace-collapsed need, tab
  format per the contract) and the `@request_app.command("list")` `list_()` command: build
  stores, stderr-warn when `requests_.quarantined`, echo `format_request_row(r)` for
  `sorted(requests_.all(), key=lambda r: r.id)`.
- [x] **Step 4 — focused verify:** same command → all new tests pass; existing store tests still green.
- [x] **Step 5 — commit:** `request: add read-only 'xsource request list' + store quarantine counters`

### Task 2: `book` CLI group — search + import (publish command arrives in Task 4)

**Files:** create `src/xsource/cli/book.py`; modify `src/xsource/cli/__init__.py`,
`src/xsource/book/search.py` (add `format_supplier_row`), `src/xsource/book/importer.py`
(add `dry_run`, widen `store` annotation); test `tests/cli/test_book_commands.py` (new),
`tests/book/test_importer.py` (extend).

**Production call site (HR9):** `app.add_typer(book_app, name="book")` in
`src/xsource/cli/__init__.py` (alongside the existing four sub-apps).

- [x] **Step 1 — failing tests** (`tests/cli/test_book_commands.py`; `_SUPPLIERS`/`_CSV` =
  Fixtures A/B):

```python
def test_book_search_prints_pinned_row(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod
    store = _seeded_suppliers(tmp_path)  # Fixture A via JsonlStore upserts
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = runner.invoke(app, ["book", "search", "heating"])
    assert result.exit_code == 0
    assert result.stdout == "s-0002\tBeta Heating\theating\tboiler\t\n"


def test_book_search_no_matches_prints_nothing(monkeypatch, tmp_path):
    ...  # term "roofing" → exit 0, stdout ""


def test_book_import_reports_and_writes(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    store.upsert(Supplier(id="s-0002", name="Beta Heating"))
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = runner.invoke(app, ["book", "import", str(csv_file)])
    assert result.exit_code == 0
    assert "{'imported': 1, 'skipped': 1}" in result.stdout
    assert {s.name for s in store.all()} == {"Beta Heating", "Gamma Roofing"}


def test_book_import_dry_run_writes_nothing(monkeypatch, tmp_path):
    ...  # same seed; ["book", "import", str(csv_file), "--dry-run"] →
    ...  # "{'imported': 1, 'skipped': 1}" in stdout AND store.all() still only Beta Heating


def test_book_import_missing_file_exits_2(...):
    ...  # ["book", "import", str(tmp_path / "absent.csv")] → exit_code == 2
```

  Plus in `tests/book/test_importer.py`: `test_import_dry_run_matches_wet_report` (dry report ==
  subsequent wet report; store untouched after dry) and
  `test_import_intra_csv_duplicate_skipped` (same name twice in one CSV → second row skipped).
- [x] **Step 2 — run, confirm RED:** `uv run pytest tests/cli/test_book_commands.py tests/book -q`
  → `No such command 'book'` and `TypeError: import_csv() got an unexpected keyword argument 'dry_run'`.
- [x] **Step 3 — implement:**
  - `book/search.py`: add `format_supplier_row` exactly per the contract.
  - `book/importer.py`: signature
    `import_csv(path, store, today, *, dry_run: bool = False) -> dict[str, int]`; in the loop,
    only the `Supplier(...)`/`store.upsert(...)` block is guarded by `if not dry_run:`; the
    dedupe bookkeeping (`existing.add`, counters) runs in both modes. Widen `store` from
    `JsonlStore` to a local `Protocol` with `all() / upsert(rec) / next_id(prefix)` so
    `SyncedStore` type-checks (`uv run mypy src` is a gate).
  - `cli/book.py`: `book_app = typer.Typer(help="Search, seed, and publish the supplier black book.")`;
    `search` and `import_` commands per the contract (quarantine stderr warning in `search`;
    `StoreOffline` → exit 1); mount in `cli/__init__.py`.
- [x] **Step 4 — focused verify:** same command → green; also
  `uv run pytest tests/cli/test_equivalent_cli_parity.py -q` (still green — registry unchanged
  so far).
- [x] **Step 5 — commit:** `book: add 'xsource book search|import' CLI (shared dry-run parser)`

### Task 3: wire the read-only walks — `request.list` + `book.search`

**Files:** modify `src/xsource/cli/cockpit.py`, `tests/test_cockpit_placeholders.py`,
`tests/cli/test_equivalent_cli_parity.py`; test `tests/walks/test_readonly_walks.py` (new).

**Production call site (HR9):** the `register_all()` placeholder loop in
`src/xsource/cli/cockpit.py:947-1007` — `request.list` and `book.search` leave the
`run=None` loop and become full `register_capability(CapabilitySpec(..., run=<handler>,
equivalent_cli=<constant>))` entries **at the same positions** (B item 2, C item 1).

- [x] **Step 1 — failing tests** (`tests/walks/test_readonly_walks.py`, house `_ctx` helper from
  `tests/walks/test_invoice_capture_walk.py`):

```python
def test_request_list_step_summary_and_rows(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod
    store = _seeded_requests(tmp_path)          # Fixture C
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = cockpit_mod._request_list_step(_ctx([]), {})
    assert result.ok is True
    assert result.data["summary"] == "1 open · 2 total"


def test_search_walk_surfaces_quarantine(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod
    path = tmp_path / "suppliers.jsonl"
    path.write_text(_VALID_ALPHA_LINE + "not json\n")   # Fixture D
    store = JsonlStore(path, Supplier)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = cockpit_mod._book_search_results_step(_ctx([]), {"term": "alpha"})
    assert result.data["summary"] == "1 match(es) for 'alpha' · quarantined: 1 corrupt line(s)"


def test_search_term_step_rejects_empty():
    result = cockpit_mod._book_search_term_step(_ctx([""]), {})
    assert result.ok is False and result.message == "No search term entered."


def test_readonly_walks_never_upsert(monkeypatch, tmp_path):
    ...  # wrap stores so upsert raises AssertionError; run both steps; no raise


def test_request_list_walk_result_via_drive(monkeypatch, tmp_path):
    from clonway_cockpit.agent import CockpitDriver
    from xsource.cli import cockpit as cockpit_mod
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    store = _seeded_requests(tmp_path)
    empty_sup = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    empty_inv = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    monkeypatch.setattr(cockpit_mod, "build_stores",
                        lambda cfg: (empty_sup, store, empty_inv))
    host = cockpit_mod._host(agent_mode=True)
    stream = CockpitDriver(host, keys=["B", "2", "y"]).run()
    results = [m for m in stream if m.kind == "walk.result"]
    assert results and results[0].meta["ok"] is True
    assert results[0].meta["message"] == "1 open · 2 total"
```

  In `tests/cli/test_equivalent_cli_parity.py` add (covers all four keys; book.import/publish
  cells go red in Task 5 if the constants drift):

```python
@pytest.mark.parametrize(
    "cap_key", ["request.list", "book.search", "book.import", "book.publish"]
)
def test_wired_walk_preflight_cli_matches_registry(cap_key: str) -> None:
    cockpit.register_all()
    spec = {c.key: c for c in registry.get_capabilities()}[cap_key]
    assert spec.equivalent_cli, f"{cap_key} should carry a real CLI string now"
    assert _preflight_equivalent_cli(cap_key) == spec.equivalent_cli
```

  *(In this task, parametrize only the two read-only keys; extend to all four in Task 5 —
  keep the final shape above.)*

  Plus the shelf-order validator (in `tests/test_cockpit_placeholders.py`, reusing its
  `_registered` fixture):

```python
def test_shelf_item_order_is_stable():
    by_shelf: dict[str, list[str]] = {}
    for cap in registry.get_capabilities():
        by_shelf.setdefault(cap.shelf, []).append(cap.key)
    assert by_shelf["A"] == ["request.new", "request.trigger", "request.reorder"]
    assert by_shelf["B"] == ["invoice.capture", "request.list", "request.sync"]
    assert by_shelf["C"] == ["book.search", "book.import"]
    assert by_shelf["D"] == ["book.publish", "partner.checkatrade"]
    assert by_shelf["E"] == ["request.outreach", "request.followup", "watcher.status"]
```

- [x] **Step 2 — run, confirm RED:** `uv run pytest tests/walks/test_readonly_walks.py tests/test_cockpit_placeholders.py tests/cli/test_equivalent_cli_parity.py -q`
  → `AttributeError: module … has no attribute '_request_list_step'`; parity test fails on
  `spec.equivalent_cli` empty.
- [x] **Step 3 — implement:** add the `_CLI_*` constants, `_quarantine_suffix`,
  `_readonly_preconditions`, `_request_list_step`, `_book_search_term_step`,
  `_book_search_results_step`, `_REQUEST_LIST_BLAST`, `_BOOK_SEARCH_BLAST`, the two
  `make_walk_handler` handlers (`total=2` / `total=3`), and swap the two registry entries in
  place (loop shrinks; order preserved). Steps import `format_request_row` /
  `format_supplier_row` — no second row format. Update `_PLACEHOLDER_STATUS_MARKERS`: remove
  `request.list` + `book.search` (leave the other two until Task 5) and fix the docstring count.
- [x] **Step 4 — focused verify:** same command → green; then
  `uv run pytest tests/test_cockpit_contract.py -q` (render/model parity + drives-clean intact).
- [x] **Step 5 — commit:** `cockpit: wire request.list + book.search walks at their shelf positions`

### Task 4: staff-directory publish flow + `xsource book publish`

**Files:** modify `src/xsource/book/publish.py`, `src/xsource/sheet/client.py`,
`src/xsource/wiring.py`, `src/xsource/cli/book.py`; test `tests/book/test_publish_flow.py` (new),
`tests/sheet/test_client_directory.py` (new), `tests/cli/test_book_commands.py` (extend).

**Production call site (HR9):** the `publish` command in `src/xsource/cli/book.py` (mounted
since Task 2). The walk call site lands in Task 5 — both consume the same
`publish_directory()`.

- [x] **Step 1 — failing tests** (`tests/book/test_publish_flow.py` uses a recording fake
  client — same style as `fake_sheet` in `tests/walks/test_request_new.py`):

```python
class _FakeClient:
    def __init__(self, *, gone: bool = False):
        self.calls: list[tuple] = []
        self.gone = gone

    def create_directory_sheet(self, title, values, folder_id, share_with):
        self.calls.append(("create", title, len(values), folder_id, share_with))
        return "SID-1", "https://sheets.example/SID-1"

    def update_directory_sheet(self, sheet_id, values):
        if self.gone:
            raise DirectorySheetGone(sheet_id)
        self.calls.append(("update", sheet_id, len(values)))


def _state_file(tmp_path):
    return SyncedFile(tmp_path / "directory-sheet.json", blob=None)


def test_publish_first_run_creates_and_persists(tmp_path):
    client = _FakeClient()
    report = publish_directory(_SUPPLIERS, state_file=_state_file(tmp_path), client=client,
                               title=DIRECTORY_TITLE, folder_id=None, share_with=None)
    assert report == {"sheet_id": "SID-1", "sheet_url": "https://sheets.example/SID-1",
                      "rows": 2, "created": True}
    assert client.calls == [("create", DIRECTORY_TITLE, 3, None, None)]
    assert json.loads((tmp_path / "directory-sheet.json").read_text())["sheet_id"] == "SID-1"


def test_publish_updates_existing_sheet(tmp_path):
    state = _state_file(tmp_path)
    save_directory_state(state, "SID-1", "https://sheets.example/SID-1")
    client = _FakeClient()
    report = publish_directory(_SUPPLIERS, state_file=state, client=client,
                               title=DIRECTORY_TITLE, folder_id=None, share_with=None)
    assert report["created"] is False and report["sheet_id"] == "SID-1"
    assert client.calls == [("update", "SID-1", 3)]


def test_publish_recreates_when_gone(tmp_path):
    state = _state_file(tmp_path)
    save_directory_state(state, "SID-GONE", "https://sheets.example/SID-GONE")
    client = _FakeClient(gone=True)
    report = publish_directory(_SUPPLIERS, state_file=state, client=client,
                               title=DIRECTORY_TITLE, folder_id=None, share_with=None)
    assert report["created"] is True and report["sheet_id"] == "SID-1"
    assert json.loads(state.path.read_text())["sheet_id"] == "SID-1"


def test_publish_empty_book_blocks(tmp_path):
    with pytest.raises(ValueError):
        publish_directory([], state_file=_state_file(tmp_path), client=_FakeClient(),
                          title=DIRECTORY_TITLE, folder_id=None, share_with=None)


def test_publish_state_save_failure_still_reports(tmp_path, monkeypatch, caplog):
    ...  # monkeypatch save_directory_state to raise OSError → report still returned,
    ...  # "state save failed" warning logged on the "xsource.book" logger


def test_publish_malformed_state_treated_as_absent(tmp_path):
    ...  # state file containing "not json" → create path, no exception
```

  `tests/sheet/test_client_directory.py` (monkeypatch `googleapiclient.discovery.build` to
  return recording stubs before constructing `SheetClient(creds=None)`):
  `test_directory_sheet_shared_read_only` (permissions body `role == "reader"`, `type ==
  "group"`, `sendNotificationEmail` False), `test_directory_values_written_raw`
  (`valueInputOption == "RAW"` on create and update), `test_update_clears_trailing_rows`
  (clear range `"A4:H"` for the 3-row Fixture A values), `test_update_404_raises_gone`
  (stub raising `HttpError`-shaped 404 → `DirectorySheetGone`),
  `test_no_share_call_when_group_unset` (share_with=None → no `permissions().create`).
  CLI (extend `tests/cli/test_book_commands.py`): `test_book_publish_cli_empty_book`
  (exit 1, stderr `no suppliers to publish`, fake client never called).
- [x] **Step 2 — run, confirm RED:** `uv run pytest tests/book/test_publish_flow.py tests/sheet/test_client_directory.py -q`
  → `ImportError: cannot import name 'publish_directory'`.
- [x] **Step 3 — implement:** per the Functional contract — `DIRECTORY_TITLE`,
  `DirectorySheetGone`, `load_directory_state`/`save_directory_state` (malformed state → `{}`),
  `publish_directory` (create-path state save wrapped in try/except → warning log, report still
  returned); `SheetClient.create_directory_sheet` / `update_directory_sheet` (404 detection:
  `getattr(exc, "status_code", None) == 404 or getattr(getattr(exc, "resp", None), "status", None) == 404`);
  `wiring.build_directory_state_file`; `book publish` CLI command using all of the above with
  `folder_id=cfg.drive_folder_id`, `share_with=cfg.staff_share_group`.
- [x] **Step 4 — focused verify:** same command + `uv run mypy src` → green.
- [x] **Step 5 — commit:** `book: staff-directory publish flow (persisted sheet id, read-only share) + CLI`

### Task 5: wire the gated walks — `book.import` + `book.publish`

**Files:** modify `src/xsource/cli/cockpit.py`, `tests/test_cockpit_placeholders.py`,
`tests/cli/test_equivalent_cli_parity.py`; test `tests/walks/test_book_walks.py` (new).

**Production call site (HR9):** the remaining two placeholder entries in `register_all()`
(C item 2, D item 1) become full registrations with `run=` handlers; the parity test's
parametrize list reaches its final four-key shape (Task 3 Step 1).

- [x] **Step 1 — failing tests** (`tests/walks/test_book_walks.py`):

```python
def test_book_import_declined_writes_nothing(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: False)
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = cockpit_mod._book_import_apply_step(_ctx([]), {"csv_path": str(csv_file)})
    assert result.ok is False and result.message == "Apply declined."
    assert store.all() == []


def test_book_import_apply_writes_and_summarises(monkeypatch, tmp_path):
    ...  # seed Beta Heating; confirm_apply → True; summary == "Imported 1, skipped 1."
    ...  # store now holds Beta Heating + Gamma Roofing


def test_book_import_rerun_is_noop(monkeypatch, tmp_path):
    ...  # run apply twice; second summary == "Imported 0, skipped 2.";
    ...  # store file bytes identical before/after the second run


def test_book_import_file_step_rejects_missing_path(tmp_path):
    result = cockpit_mod._book_import_file_step(_ctx([str(tmp_path / "absent.csv")]), {})
    assert result.ok is False and result.message.startswith("No such file:")


def test_book_import_preflight_blocks_offline(monkeypatch):
    ...  # stores with .offline=True → _book_write_preconditions has a not-ok row


def test_book_publish_declined_writes_nothing(monkeypatch, tmp_path):
    ...  # confirm_apply → False; a sentinel publish_directory that raises AssertionError
    ...  # if called; result.message == "Apply declined."


def test_book_publish_apply_summary(monkeypatch, tmp_path):
    ...  # monkeypatch cockpit publish collaborators (SheetClient → _FakeClient,
    ...  # Credentials.from_authorized_user_file → stub); confirm_apply → True;
    ...  # summary == "Published directory (2 supplier(s))."
    ...  # result_links == [("Directory", "https://sheets.example/SID-1")]


def test_publish_apply_step_reports_api_error(monkeypatch, tmp_path):
    ...  # publish_directory raising RuntimeError("boom") → ok=False,
    ...  # message == "Publish failed: boom"


def test_book_publish_preview_blocks_empty_book(monkeypatch, tmp_path):
    ...  # empty suppliers → ok=False, "No suppliers in the black book."
```

- [x] **Step 2 — run, confirm RED:** `uv run pytest tests/walks/test_book_walks.py tests/cli/test_equivalent_cli_parity.py -q`.
- [x] **Step 3 — implement:** `_book_write_preconditions`, `_publish_preconditions`,
  `_book_import_file_step` / `_book_import_preview_step` (calls `import_csv(..., dry_run=True)`)
  / `_book_import_apply_step` (gate → wet `import_csv`; `StoreOffline` → `ok=False`),
  `_book_publish_preview_step` / `_book_publish_apply_step` (gate → `publish_directory` via
  `build_directory_state_file` + `SheetClient`; `Exception` → `f"Publish failed: {exc}"`),
  `_BOOK_IMPORT_BLAST`, `_BOOK_PUBLISH_BLAST`, two handlers (`total=4` / `total=3`), swap the
  last two placeholder entries in place. Remove `book.import`/`book.publish` from
  `_PLACEHOLDER_STATUS_MARKERS` (leaving `request.sync`, `watcher.status`,
  `partner.checkatrade`, `doctor`); extend the parity parametrize to the final four keys.
- [x] **Step 4 — focused verify:** `uv run pytest tests/walks tests/test_cockpit_placeholders.py tests/cli/test_equivalent_cli_parity.py tests/test_cockpit_contract.py -q` → green.
- [x] **Step 5 — commit:** `cockpit: wire gated book.import + book.publish walks (confirm-apply writes)`

### Task 6: operator docs for the new surfaces

**Files:** modify `README.md`, `docs/cockpit-journeys.md`.

- [x] README "CLI surface" fence: append exactly four lines —
  `xsource request list` (list procurement requests, read-only), `xsource book search TERM`,
  `xsource book import CSV [--dry-run]`, `xsource book publish` — matching the command help
  strings. Touch nothing else in README (doc-truth PR owns the rest).
- [x] `docs/cockpit-journeys.md`: update the **Requests**, **Black book**, and **Publish**
  journey sections — the four capabilities move from "placeholder" to "implemented", each
  naming its walk steps, gate (or read-only), and CLI twin; remove rows 1, 4, 5, 6 from the
  Follow-up scoping table (rows 2, 3, 7, 8 remain, renumbered 1–4).
- [x] Verification (paste output): `grep -n "book search\|book import\|book publish\|request list" README.md docs/cockpit-journeys.md`
  and `grep -c "Planned — not yet wired" src/xsource/cli/cockpit.py` → `0`.
- [x] **Commit:** `docs: cockpit journeys + README reflect wired request.list/book walks`

### Task 7: full gates + RUNBOOK DELTA

- [ ] Run the four canonical gates from the repo root, verbatim, and paste the output tails in
  the DONE comment: `uv run pytest -q` · `uv run ruff check .` · `uv run ruff format --check .`
  · `uv run mypy src` (expect ≥ 286 + ~30 new tests passing, 0 lint/type errors).
- [ ] Post on `hearth-care/auto-orchestrator#196` and repeat verbatim in the DONE comment:
  `RUNBOOK DELTA (auto-procurer): new operator surfaces — 'xsource request list' and 'xsource
  book search|import|publish' CLI commands; cockpit shelves B/C/D now run live walks for
  request.list, book.search, book.import, book.publish. Import and publish are gated writes
  behind confirm-apply (publish shares the staff directory read-only); search/list are
  read-only.`
- [ ] `gh pr ready` + flip label to `agent:needs-qa` + single DONE comment per the worker
  contract.

---

## Self-Review

- **Spec coverage:** CLI contract → Tasks 1–2, 4; walks → Tasks 3, 5; publish flow → Task 4;
  docs → Task 6; every HR5 checkbox names the task that lands its test.
- **Safety invariants:** 14-cell table above, each bound to a named test; both writes carry
  idempotency key + partial-failure path (HR4); no money movement anywhere.
- **Tests are load-bearing (HR8):** CLI tests assert exact stdout/stderr/exit codes; walk tests
  assert `StepResult.ok/message/data` and one full `CockpitDriver` run asserts the rendered
  `walk.result` frame message; write-gate tests assert the store/file state, not call counts
  alone. Each Step 2 names the RED signal proving the test bites.
- **Wired end-to-end (HR9):** every handler is registered at its shelf position in
  `register_all()` (validated by `test_shelf_item_order_is_stable`), every CLI command mounted
  on the root app (validated by the parity `--help` gate); no helper without a caller.
- **Snippets (HR10):** fixtures/ids/ranges computed in the worked examples (`s-0003`, `A4:H`,
  `rows=2`); no magic pads; 404 detection handles both `HttpError` shapes.
- **Gates (HR2):** the four exact CI commands, stated twice (Global Constraints + Task 7).
- **Runbook (HR1):** operator-facing — RUNBOOK DELTA checkbox in Task 7 with the exact text.
- **Waves (HR11):** no unmerged dependency → no wave tag; doc-truth PR independence stated.
- **Deferred:** request.sync walk / sync-all dry-run, watcher.status card, doctor probes,
  partner.checkatrade — named non-goals mapping to journey-map follow-up rows.

## HANDOFF NOTES

- Current phase: Task 6 complete; starting Task 7 (full gates, runbook delta, PR finish protocol).
- Next concrete step: run canonical gates from repo root, then rebase onto latest `origin/main`.
- Decisions taken: Task 1 followed the plan as written; Task 2 added only `book search` and `book import` CLI; Task 3 wired `request.list` and `book.search` at their existing shelf positions; Task 4 added the publish flow/CLI; Task 5 wired the remaining gated book walks through `confirm_apply`; Task 6 updated only the new command lines and journey-map sections named by the plan.
- Known failing tests: none after Task 6 grep verification (`request list`/`book search`/`book import`/`book publish` lines present; `Planned — not yet wired` count in `src/xsource/cli/cockpit.py` is `0`).
- Dependencies/operator TODOs: none.
