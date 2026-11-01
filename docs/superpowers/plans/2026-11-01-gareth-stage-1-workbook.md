# Gareth stage 1: the lasting workbook and the Board — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Sheet-per-search with one lasting workbook (Board, a tab per job, Black book, Log), redrawn from the store, with Gareth's name on the drafts and the four live-run faults fixed.

**Architecture:** The store stays the record. A new `xsource.workbook` package turns store records into tab grids (pure functions), writes them through one Sheets client, and reads the hand-editable columns back before every redraw. Every event that changes a job (apply, draft sent, reply, sheet edit) updates stored stages through one `advance()` function, then redraws. The contract files are parsed by a test, so the code cannot drift from them.

**Tech Stack:** Python 3.12, `uv`, Google Sheets v4 / Drive v3 via the existing OAuth token (`XSOURCE_SHEETS_TOKEN_PATH`), `clonway-cockpit` walks, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-gareth-design.md`, with `docs/contracts/gareth-workbook-v1.md`, `gareth-screens-v1.md`, `gareth-calls-v1.md` and the mock-up `docs/superpowers/specs/2026-11-01-gareth/sheet-layout.html`.

## Stages (one plan each; only stage 1 is detailed here)

| Stage | Delivers | New Google access needing approval |
|---|---|---|
| **1 (this plan)** | workbook, Board page, stored stages, Gareth's name, live-run fixes | none — existing Sheets/Drive/Gmail token |
| 2 | phone calls: transcript matching, Call list and Calls to file pages | read the transcripts folder |
| 3 | Google Chat DM, cards, nudges, morning note; haggle and booking drafts | the Chat app |
| 4 | Drive filing: job folders in `_Shortlists`, supplier folders, call copies | write to the Suppliers folders |
| 5 | `supplier.new` hand-off to Milo and the In Xero tick | none here; a matching PR in the bookkeeper repo |

Each later stage gets its own plan, written after the previous stage merges, and does not start until the operator has approved its Google access.

## Global Constraints

- Draft-never-send: nothing sends email; `tests/test_no_send_endpoints.py` stays green.
- Every mutating cockpit walk goes through `confirm_apply`; `--agent-stdio` stays dry-run without `--allow-apply`.
- Public repo: fixtures use made-up firms and `07700 900xxx` / `01632 960xxx` numbers only.
- The store is the record; the Sheet is redrawn from it. Never write a value to the Sheet that is not first in the store.
- Phone cells are text: the leading 0 must survive (`'` prefix under `USER_ENTERED`).
- Contract files change in the same commit as the code they describe; renaming, removing or reordering an existing column or tab bumps `contract_version`.
- Commits use the local git identity with no Co-Authored-By or "Generated with" lines.
- Verification command, run from the repo root with an empty state dir:
  `XSOURCE_STATE_DIR=$(mktemp -d) uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy`

## Review Focus

1. **Job or firm names with an apostrophe or Sheet-forbidden characters** (`O'Neill Electrical`, `Gas/Heating: annual`): the tab is still created and Board formulas still resolve (quote doubled inside `'…'`, `[]*?:/\` stripped). → Task 4.
2. **A job with no prices yet**: Best price and Best firm show blank, never `£0` or `#N/A`. → Task 1 (contract) and Task 4.
3. **Phone numbers in any shape** (`+447700900001`, `01632 960001`, `07700900001`): written as text with the leading 0, never parsed as a number or formula. → Task 4.
4. **Operator hand-edits that move or mangle rows** (rows sorted, a price typed as `£1,250.50`, a firm name typed in that Gareth doesn't know): readback matches by Firm, not row position; money parses to pence; an unknown firm row is reported as a warning and creates nothing. → Task 6.
5. **Two jobs of the same kind in one month, and legacy requests**: the second tab gets ` (2)`; a request with only a legacy `sheet_id` and no `job_tab` is never written to. → Tasks 4 and 6.

---

### Task 1: Contract test and workbook constants

**Files:**
- Create: `src/xsource/workbook/__init__.py` (empty), `src/xsource/workbook/contract.py`
- Create: `tests/test_gareth_contracts.py`
- Modify: `docs/contracts/gareth-workbook-v1.md`

**Interfaces:**
- Produces, in `xsource.workbook.contract`: `CONTRACT_VERSION: int = 1`; `FIXED_TABS = ("Board", "Black book", "Log")`; `BOARD_COLUMNS`, `JOB_COLUMNS`, `ENERGY_JOB_COLUMNS`, `BLACK_BOOK_COLUMNS`, `LOG_COLUMNS: tuple[str, ...]` (headers in order); `FIRM_STAGES`, `JOB_STAGES: tuple[str, ...]`; `KEEN_STAGES = ("Keen", "Emailed", "Quoted", "Booked")`; `JOB_HAND_EDITABLE = ("Contact", "Phone", "Email", "Stage", "First price", "Latest price", "Notes")` (energy adds `Term`, `Unit rate`, `Standing charge`, `Est. yearly cost`); `BLACK_BOOK_HAND_EDITABLE = ("Contact", "Phone", "Email", "Contract ends", "Notice to give")`; `price_header(energy: bool) -> str`.
- Produces, in the test module: `parse_contract_tables(path: Path) -> dict[str, list[dict[str, str]]]`, keyed by the `##` heading each table follows.

- [ ] **Step 1: Fix the workbook contract so it parses and never shows £0**

In `gareth-workbook-v1.md`: move the `<P>` explanation paragraph below the Board table so rows H and I are inside it; change F to `=IF(E<r>=0,"",MIN('<tab>'!<P>:<P>))` and G to `=IF(E<r>=0,"",INDEX('<tab>'!B:B, MATCH(MIN('<tab>'!<P>:<P>), '<tab>'!<P>:<P>, 0)))`, and J in Black book to `=IF(H<r>="","",H<r>-I<r>)`, with a line saying `<r>` is the row number. No `contract_version` bump: no column was renamed, removed or reordered.

- [ ] **Step 2: Write the failing tests**

```python
WORKBOOK = Path("docs/contracts/gareth-workbook-v1.md")

def test_tab_names_match_contract():
    tabs = parse_contract_tables(WORKBOOK)["Tabs"]
    assert tuple(r["Tab name"].strip("`") for r in tabs[:3]) == contract.FIXED_TABS

@pytest.mark.parametrize("heading, columns", [
    ("Board", contract.BOARD_COLUMNS),
    ("Job tab (standard trades)", contract.JOB_COLUMNS),
    ("Black book", contract.BLACK_BOOK_COLUMNS),
    ("Log", contract.LOG_COLUMNS),
])
def test_columns_match_contract(heading, columns):
    rows = parse_contract_tables(WORKBOOK)[heading]
    assert tuple(r["Header"] for r in rows) == columns
    assert [r["Col"] for r in rows] == [chr(ord("A") + i) for i in range(len(columns))]

def test_energy_columns_replace_prices_and_shift_by_two():
    assert contract.ENERGY_JOB_COLUMNS[9:13] == ("Term", "Unit rate", "Standing charge", "Est. yearly cost")
    assert contract.ENERGY_JOB_COLUMNS[13:] == contract.JOB_COLUMNS[11:]

def test_stages_match_contract():
    text = WORKBOOK.read_text()
    assert all(f"`{s}`" in text for s in contract.FIRM_STAGES + contract.JOB_STAGES)
    assert contract.FIRM_STAGES[0] == "To call" and contract.JOB_STAGES[-1] == "Done"

def test_contract_version_matches():
    assert f"contract_version: {contract.CONTRACT_VERSION}" in WORKBOOK.read_text()
```

Task 4 adds the formula assertions; Task 9 adds the screens check.

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_gareth_contracts.py -v` → FAIL, `ModuleNotFoundError: xsource.workbook`.
- [ ] **Step 4: Write `contract.py` and `parse_contract_tables`** (split each Markdown table under the preceding `##`/`###` heading text; header row gives the keys; strip backticks only in callers).
- [ ] **Step 5: Run to verify pass** — same command → PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(workbook): contract constants and a test that parses the contract"`

### Task 2: Store schema v2 and the Log store

**Files:**
- Modify: `src/xsource/store/models.py`, `src/xsource/wiring.py`
- Test: `tests/store/test_models.py`

**Interfaces:**
- Produces on `Request`: `schema_version: int = 2`, `title: str | None` (short label, e.g. `"EICR"`), `stage: str = "Searching"`, `job_tab: str | None`, `job_tab_gid: int | None`, `energy: bool = False`, `next_step: str = ""`, `waiting_on: str = "Nobody"`.
- Produces on `ShortlistEntry`: `stage: str = "To call"`, `miles: float | None`, `first_price_minor: int | None`, `latest_price_minor: int | None`, `energy_quote: dict[str, Any]` (keys `term`, `unit_rate`, `standing_charge`, `yearly_cost_minor`), `last_contact: dict[str, str]` (`{"date": ISO date, "via": "call" | "email"}`), `call_ids: list[str]`, `contact_name: str | None`, `notes: str = ""`.
- Produces on `Supplier`: `schema_version: int = 2`, `contact_name: str | None`, `drive_folder_id: str | None`, `contract_ends: str | None` (ISO date), `notice_days: int | None`, `in_xero: bool = False`.
- Produces: `@dataclass class LogEntry: id: str; at: str; request_id: str | None; text: str` with `to_dict`/`from_dict`; `build_log_store(cfg: Config) -> SyncedStore` in `wiring.py` (`log.jsonl`, id prefix `l`). `build_stores` keeps its three-tuple signature.

- [ ] **Step 1: Write the failing tests**

```python
def test_v1_request_upgrades_on_read():
    old = {"id": "r-0001", "created_at": "2026-10-31T16:20:00+00:00", "raw_need": "EICR",
           "status": "open", "sheet_id": "legacy", "shortlist": [
               {"supplier_id": "s-0001", "rank": 1, "outreach": {"status": "asked"}},
               {"supplier_id": "s-0002", "rank": 2, "reply": {"status": "quoted", "quote_amount": 780}},
               {"supplier_id": "s-0003", "rank": 3}]}
    req = Request.from_dict(old)
    assert req.schema_version == 2
    assert [e.stage for e in req.shortlist] == ["Emailed", "Quoted", "To call"]
    assert req.shortlist[1].latest_price_minor == 78000
    assert req.shortlist[1].first_price_minor == 78000
    assert req.job_tab is None and req.sheet_id == "legacy"

def test_v2_round_trips_unchanged():
    req = Request(id="r-0002", created_at="2026-11-01T09:00:00+00:00", raw_need="x", title="EICR",
                  stage="Calling", shortlist=[ShortlistEntry(supplier_id="s-1", rank=1, stage="Keen", miles=3.2)])
    assert Request.from_dict(req.to_dict()) == req

def test_closed_v1_request_with_chosen_supplier_upgrades_to_done_and_booked():
    ...  # status closed + chosen_supplier_id s-0002 → stage "Done"; s-0002 entry "Booked", others "Not chosen"

def test_log_entry_round_trips():
    e = LogEntry(id="l-0001", at="2026-11-01T09:00:00+00:00", request_id="r-0001", text="Job tab created")
    assert LogEntry.from_dict(e.to_dict()) == e
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/store/test_models.py -v` → FAIL on unknown field `schema_version`.
- [ ] **Step 3: Implement the fields and `_upgrade_v1(d) -> d` inside `Request.from_dict`** (runs only when `schema_version` is missing or 1). v1 mapping: `outreach.status == "asked"` → `Emailed`; `draft_ready` → `Keen`; `reply.status` `quoted` → `Quoted` with both prices from `quote_amount × 100`; `reply.declined` or `no` → `Declined`; closed with chosen → that entry `Booked`, other entries `Not chosen`, job `Done`; open with any `Emailed`/`Quoted` → job `Waiting for prices`, else `Calling`. Suppliers just gain defaults. Add `LogEntry` and `build_log_store`.
- [ ] **Step 4: Run to verify pass**, then the whole suite (the upgrade touches every loader).
- [ ] **Step 5: Commit** — `git commit -m "feat(store): schema v2 with stored stages, prices in pence and a log"`

### Task 3: One function that moves stages on

**Files:**
- Create: `src/xsource/workbook/stages.py`
- Test: `tests/workbook/test_stages.py` (create `tests/workbook/__init__.py`)

**Interfaces:**
- Consumes: Task 2 fields, `contract.FIRM_STAGES`, `contract.JOB_STAGES`.
- Produces: `record_price(entry: ShortlistEntry, amount_minor: int, *, on: dt.date, via: str) -> None` (sets `first_price_minor` only if empty, always `latest_price_minor`, stage `Quoted`, `last_contact`); `advance(request: Request) -> list[str]` (recomputes `request.stage`, `next_step`, `waiting_on` from the entries and returns Log lines describing what changed, empty when nothing did).

- [ ] **Step 1: Write the failing tests**

```python
def test_new_job_is_calling_with_firms_to_ring():
    r = _request(stages=["To call", "To call", "To call"])
    assert advance(r) == ["Stage: Searching → Calling"]
    assert r.next_step == "Ring 3 firms on the call list"
    assert r.waiting_on == "You: ring 3 firms"

def test_any_emailed_firm_moves_job_to_waiting_for_prices():
    r = _request(stages=["Emailed", "No answer", "Declined"], job_stage="Calling")
    advance(r)
    assert r.stage == "Waiting for prices" and r.waiting_on == "Nobody"

def test_booked_firm_marks_others_not_chosen_and_job_booked():
    r = _request(stages=["Booked", "Quoted", "Keen"], job_stage="Waiting for prices")
    advance(r)
    assert [e.stage for e in r.shortlist] == ["Booked", "Not chosen", "Not chosen"]
    assert r.stage == "Booked"

def test_first_price_is_kept_when_a_better_price_arrives():
    e = ShortlistEntry(supplier_id="s-1", rank=1)
    record_price(e, 78000, on=dt.date(2026, 11, 2), via="email")
    record_price(e, 72000, on=dt.date(2026, 11, 5), via="email")
    assert (e.first_price_minor, e.latest_price_minor) == (78000, 72000)
    assert e.last_contact == {"date": "2026-11-05", "via": "email"}

def test_advance_twice_logs_nothing_the_second_time():
    r = _request(stages=["To call"])
    advance(r)
    assert advance(r) == []

def test_closed_request_is_done():
    ...  # status "closed" → stage "Done", next_step "", waiting_on "Nobody"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/workbook/test_stages.py -v` → FAIL, module missing.
- [ ] **Step 3: Implement.** Job stage rules, in order: closed → `Done`; any entry `Booked` → `Booked` (others not `Declined` become `Not chosen`); any `Emailed`/`Quoted` → `Waiting for prices`; else `Calling`. `Haggling` is set by stage 3 only and `advance` leaves it alone while no firm is `Booked`. Next step and waiting-on copy: `Calling` → `Ring N firms on the call list` / `You: ring N firms` (N = entries in `To call` or `No answer`); `Waiting for prices` → `Wait for prices (Q of K in)` / `Nobody`; `Booked` → `Confirm the date with <firm>` / `You: confirm the date`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(workbook): stored job and firm stages moved on by one function"`

### Task 4: Tab grids, formulas and names

**Files:**
- Create: `src/xsource/workbook/layout.py`
- Test: `tests/workbook/test_layout.py`; extend `tests/test_gareth_contracts.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `job_tab_name(title: str, created: dt.date, existing: set[str]) -> str` — `"EICR Nov 2026"`, `"EICR Nov 2026 (2)"` on clash; strips `[]*?:/\`; at most 90 characters.
  - `quote_tab(name: str) -> str` — `"'O''Neill Nov 2026'"`.
  - `phone_cell(phone: str | None) -> str` — `"'01632 960001"`; `""` for none; `+44` → `0`, spaces in UK groupings (reuse the grouping from `xsource.cli.cockpit._uk_phone`, moved here and imported back there).
  - `board_rows(requests: list[Request], start_row: int = 2) -> list[list[str]]` (open jobs only, newest first, header excluded).
  - `job_tab_rows(request: Request, suppliers: dict[str, Supplier]) -> list[list[str]]` (header included; energy layout when `request.energy`).
  - `black_book_rows(suppliers: list[Supplier], requests: list[Request]) -> list[list[str]]` (header included).
  - `log_rows(entries: list[LogEntry], requests: dict[str, Request]) -> list[list[str]]` (header included, newest first).

- [ ] **Step 1: Write the failing tests**

```python
def test_board_formulas_match_contract_with_row_numbers():
    row = board_rows([_job("EICR Nov 2026")], start_row=2)[0]
    assert row[3] == "=COUNTIF('EICR Nov 2026'!I:I,\"Keen\")+COUNTIF('EICR Nov 2026'!I:I,\"Emailed\")+COUNTIF('EICR Nov 2026'!I:I,\"Quoted\")+COUNTIF('EICR Nov 2026'!I:I,\"Booked\")"
    assert row[4] == "=COUNT('EICR Nov 2026'!K2:K)"
    assert row[5] == "=IF(E2=0,\"\",MIN('EICR Nov 2026'!K:K))"
    assert row[6].startswith("=IF(E2=0,\"\",INDEX('EICR Nov 2026'!B:B, MATCH(")

def test_energy_job_board_reads_yearly_cost_column():
    row = board_rows([_job("Electricity Nov 2026", energy=True)])[0]
    assert "'Electricity Nov 2026'!M:M" in row[5]

def test_apostrophe_in_tab_name_is_doubled_in_formulas():
    row = board_rows([_job("O'Neill check Nov 2026")])[0]
    assert "'O''Neill check Nov 2026'!I:I" in row[3]

def test_tab_name_strips_forbidden_characters_and_numbers_clashes():
    d = dt.date(2026, 11, 1)
    assert job_tab_name("Gas/Heating: annual", d, set()) == "GasHeating annual Nov 2026"
    assert job_tab_name("EICR", d, {"EICR Nov 2026"}) == "EICR Nov 2026 (2)"

@pytest.mark.parametrize("raw, cell", [
    ("+447700900001", "'07700 900001"), ("01632 960001", "'01632 960001"),
    ("07700900001", "'07700 900001"), (None, ""),
])
def test_phone_cells_keep_the_leading_zero(raw, cell):
    assert phone_cell(raw) == cell

def test_job_tab_row_shows_prices_in_pounds_and_last_contact():
    rows = job_tab_rows(_job_with_quote(first=78000, latest=72000, on="2026-11-05", via="email"), _suppliers())
    assert rows[0] == list(contract.JOB_COLUMNS)
    assert rows[1][9:12] == ["780", "720", "5 Nov · email"]

def test_black_book_tell_them_by_formula_per_row():
    rows = black_book_rows([_supplier(contract_ends="2027-03-31", notice_days=90)], [_closed_job()])
    assert rows[1][9] == "=IF(H2=\"\",\"\",H2-I2)"

def test_log_newest_first():
    ...
```

In `tests/test_gareth_contracts.py` add `test_board_formula_shapes_match_contract`: the D–G source cells in the contract, with `<tab>`, `<P>` and `<r>` substituted, equal `board_rows` output for one standard and one energy job.

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/workbook/test_layout.py tests/test_gareth_contracts.py -v` → FAIL, module missing.
- [ ] **Step 3: Implement** the functions. Prices are written in pounds: whole pounds without decimals (`"780"`), otherwise two decimals (`"1250.50"`); the `£` comes from the column format in Task 5. Board column B is `=HYPERLINK("#gid=<job_tab_gid>","<job_tab>")`; job tab N is `=HYPERLINK("https://mail.google.com/mail/u/0/#all/<thread_id>","thread")` when a thread exists; M (Calls) stays blank until stage 2. Black book: one row per kind of job, where kind is the triage `category` of the newest closed request that chose the firm, or the first of `supplier.categories` for a `preferred` firm; the newest firm wins per kind; L links to that request's job tab.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(workbook): Board, job, black book and log grids with contract formulas"`

### Task 5: Workbook Sheets client

**Files:**
- Create: `src/xsource/workbook/client.py`
- Test: `tests/workbook/test_client.py` (fake `sheets` service recording calls, in the style of `tests/sheet/test_client_updates.py`)

**Interfaces:**
- Produces `class WorkbookClient`, built like `SheetClient` from creds:
  - `create(title: str, folder_id: str | None) -> tuple[str, str]` — new spreadsheet with the three fixed tabs in contract order; returns id and URL.
  - `tab_ids(workbook_id: str) -> dict[str, int]` — tab name → gid.
  - `ensure_tab(workbook_id: str, name: str, *, index: int) -> int` — adds the tab if missing, returns gid.
  - `write_tab(workbook_id: str, name: str, rows: list[list[str]]) -> None` — `USER_ENTERED`, then clears below the last row.
  - `read_tab(workbook_id: str, name: str) -> list[list[str]]` — `FORMATTED_VALUE`.
  - `format_tab(workbook_id: str, gid: int, kind: Literal["board", "job", "energy", "black_book", "log"]) -> None` — header bold and frozen; `£` number format on price columns; warning-only protected ranges on the contract's protected columns; Black book J red when `=AND(J2<>"",J2-TODAY()<60)`; Stage column validation from `FIRM_STAGES`.

- [ ] **Step 1: Write the failing tests** — `create` sends tabs `["Board", "Black book", "Log"]` in order; `ensure_tab` issues no `addSheet` when the name exists; `write_tab` uses `valueInputOption="USER_ENTERED"` and a clear starting at `len(rows)+1`; `format_tab("black_book")` includes a conditional format whose formula is exactly `=AND(J2<>"",J2-TODAY()<60)`; protected ranges carry `warningOnly: True` (the token's account owns the file, so hard protection would not stop the operator anyway; the warning is the guard).
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(workbook): Sheets client for the lasting workbook"`

### Task 6: Readback, redraw, migration and the CLI

**Files:**
- Create: `src/xsource/workbook/readback.py`, `src/xsource/workbook/redraw.py`, `src/xsource/cli/workbook.py`
- Modify: `src/xsource/config.py` (add `workbook_id: str | None` from `XSOURCE_WORKBOOK_ID`), `src/xsource/cli/__init__.py` (mount `workbook_app`), `src/xsource/cli/request.py` (`sync-all` calls `redraw_workbook` when `workbook_id` is set; per-request legacy sync stays only for the one-off migration), `deploy/xsource-cloud-run.env.example` (add `XSOURCE_WORKBOOK_ID=`)
- Test: `tests/workbook/test_readback.py`, `tests/workbook/test_redraw.py`, `tests/cli/test_workbook_cli.py`

**Interfaces:**
- Consumes: Tasks 2–5; the existing `SheetClient.read_request_rows` for migration only.
- Produces:
  - `read_job_edits(rows: list[list[str]], request: Request, suppliers: dict[str, Supplier], *, on: dt.date) -> list[str]` — applies hand edits to the store objects, matched by Firm; returns warnings.
  - `read_black_book_edits(rows: list[list[str]], suppliers: list[Supplier]) -> list[str]`.
  - `parse_money_minor(text: str) -> int | None` — `"£1,250.50"` → `125050`; `""`/`"tbc"` → `None`.
  - `redraw_workbook(*, workbook_id: str, client: WorkbookClient, suppliers, requests, log, now: dt.datetime) -> dict[str, Any]` — for every request with a `job_tab`: read back edits, `advance`, save, write its tab; then Board, Black book, Log. Returns `{"jobs": n, "warnings": [...]}`. Requests without `job_tab` are skipped.
  - `migrate_open_requests(*, workbook_id, client, legacy_sheets: SheetClient, suppliers, requests, log, now) -> list[str]` — for each open request with a `sheet_id` and no `job_tab`: one final legacy readback, then title from `triage.category`, tab created, `job_tab`/`job_tab_gid` saved, Log line `Moved from its old Sheet`. The legacy Sheet is not modified.
  - CLI: `xsource workbook init` (creates the workbook in `XSOURCE_DRIVE_FOLDER_ID`, prints `export XSOURCE_WORKBOOK_ID=<id>`), `xsource workbook redraw`, `xsource workbook migrate --apply` (dry-run list without `--apply`).

- [ ] **Step 1: Write the failing tests**

```python
def test_edits_match_by_firm_even_after_rows_are_sorted():
    rows = [list(JOB_COLUMNS), _row(firm="Example Sparks Ltd", latest="£1,250.50"), _row(firm="Acme Testing", stage="Declined")]
    req = _job(firms=["Acme Testing", "Example Sparks Ltd"])
    assert read_job_edits(rows, req, _suppliers(), on=dt.date(2026, 11, 3)) == []
    assert _entry(req, "Example Sparks Ltd").latest_price_minor == 125050
    assert _entry(req, "Acme Testing").stage == "Declined"

def test_unknown_firm_row_is_a_warning_and_creates_nothing():
    rows = [list(JOB_COLUMNS), _row(firm="Someone New")]
    req = _job(firms=["Acme Testing"])
    assert read_job_edits(rows, req, _suppliers(), on=dt.date(2026, 11, 3)) == ["EICR Nov 2026: no firm called 'Someone New' on this job"]
    assert len(req.shortlist) == 1

def test_stage_typed_outside_the_list_is_ignored_with_a_warning(): ...

def test_phone_edit_is_saved_to_the_supplier(): ...  # "'01632 960002" → supplier.phone "01632 960002"

def test_redraw_reads_back_before_writing_and_skips_legacy():
    client = FakeWorkbookClient(tabs={"EICR Nov 2026": [...edited price...]})
    report = redraw_workbook(workbook_id="wb", client=client, suppliers=..., requests=_stores(legacy=True), log=..., now=NOW)
    assert client.calls[0] == ("read_tab", "EICR Nov 2026")
    assert ("write_tab", "Board") in client.calls
    assert not any(name == "Old request" for _, name in client.calls)
    assert report["jobs"] == 1

def test_redraw_with_no_changes_adds_no_log_lines(): ...

def test_migrate_dry_run_changes_nothing(): ...
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Readback writes only the hand-editable columns named in the contract; any other differing cell is overwritten by the redraw. Price edits go through `record_price` with `via` unchanged from the entry's last contact.
- [ ] **Step 4: Run to verify pass, then the whole suite.**
- [ ] **Step 5: Commit** — `git commit -m "feat(workbook): read back hand edits, redraw from the store, migrate open requests"`

### Task 7: New requests become job tabs, with the shortlist shown first

**Files:**
- Modify: `src/xsource/walks/request_new.py`, `src/xsource/cli/cockpit.py` (`_review_apply_step`, `_preconditions`, `_research_step`), `src/xsource/research/triage.py` (add `short_label` to the schema: required string, at most 20 characters, e.g. `"EICR"`)
- Test: `tests/walks/test_request_new.py`, `tests/research/test_triage.py`

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces: `apply_request(..., add_job_tab_fn: Callable[[Request], tuple[str, int]], log, ...)` replaces `create_sheet_fn` (`add_job_tab_fn` returns the tab name and gid; `log` is the Task 2 log store). It saves the request with `title = triage["short_label"]`, `energy = triage["category"] == "energy"`, each entry's `miles` from `candidate.extra["miles"]`, then `advance`, `add_job_tab_fn`, a Log line, and returns the request. `shortlist_preview_rows(cands: list[Candidate]) -> list[str]` returns one line per firm (`#  firm  miles  phone  source`).

- [ ] **Step 1: Write the failing tests** — the review step prints `shortlist_preview_rows` before `confirm_apply` is called (assert the order with a recording `confirm_fn`); declining creates no tab and no store records; applying calls `add_job_tab_fn` once and leaves the request at stage `Calling` with `job_tab` set; with `XSOURCE_WORKBOOK_ID` unset the walk's precondition fails with remedy `xsource workbook init`; `miles` is copied from places candidates and `None` for black-book matches.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** In the cockpit, `add_job_tab_fn` uses `job_tab_name` with the workbook's existing tab names, `ensure_tab` at index 3 (newest job first, after the fixed tabs), `format_tab`, then `redraw_workbook`. Update `_REQUEST_NEW_BLAST.summary` to "Adds one job tab to the workbook and saves the request and its firms. Does not send or draft any email."
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(request): a new job is a workbook tab, and the shortlist is shown before it is made"`

### Task 8: Watcher — a draft is not a sent email, and events redraw

**Files:**
- Modify: `src/xsource/watcher/gmail.py`, `src/xsource/watcher/daemon.py`, `src/xsource/watcher/apply.py`, `src/xsource/cli/watcher.py`
- Test: `tests/watcher/` (extend the existing daemon and gmail tests)

**Interfaces:**
- Consumes: Tasks 3 and 6.
- Produces: `WatcherMessage.is_draft: bool` (true when the message's `labelIds` contains `"DRAFT"`). `mark_thread_sent` also sets entry stage `Emailed` and `last_contact` `{"via": "email"}`; `apply_reply_to_request` calls `record_price` when there is a `quote_amount` and sets `Declined` on a decline. The daemon takes `redraw_fn: Callable[[], None] | None` in place of writing legacy Sheets, and calls it once per cycle after `requests.upsert` when anything changed.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_draft_in_the_thread_is_not_counted_as_sent():
    gmail = FakeGmail(thread=[_msg(from_=OWN, labels=["DRAFT"])])
    run_cycle(..., gmail=gmail, redraw_fn=redraw)
    assert _entry(req).stage == "Keen" and not redraw.called

def test_the_sent_message_moves_the_firm_to_emailed_and_redraws_once():
    gmail = FakeGmail(thread=[_msg(from_=OWN, labels=["SENT"])])
    run_cycle(..., gmail=gmail, redraw_fn=redraw)
    assert _entry(req).stage == "Emailed" and redraw.call_count == 1

def test_a_quoted_reply_records_the_price_in_pence(): ...  # quote_amount 780 → latest_price_minor 78000, stage "Quoted"

def test_legacy_request_sheet_is_never_written(): ...  # request with sheet_id only: no sheets.* calls
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Remove the `mark_asked`, `write_reply` and `update_heartbeat` calls from the daemon; delete those methods from `SheetClient` if nothing else uses them. Keep `request.watcher["last_checked_at"]`. The draft rule is the cause of the "Asked before it was sent" fault from the 31 October run: Gmail lists draft messages in their thread, and they come from our own address. [ASSUMPTION: confirm against one live thread with `threads.get` before merging, recorded in the PR.]
- [ ] **Step 4: Run to verify pass, then the whole suite.**
- [ ] **Step 5: Commit** — `git commit -m "fix(watcher): count a firm as emailed only once the draft is sent, then redraw the workbook"`

### Task 9: Board page and a workbook probe

**Files:**
- Modify: `src/xsource/cli/cockpit.py` (`register_all`, the doctor probes, the Home needs-you list)
- Test: `tests/walks/test_readonly_walks.py`, `tests/test_doctor_probes.py`, `tests/test_gareth_contracts.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: capability `board` on shelf B, listed first, title "Board", a read-only walk (`BlastRadius(summary="Writes nothing.", reversible="No write is performed.", writes=False)`) whose result rows are `job · stage · quotes in · best price (firm) · waiting on`, computed from the store with the same rules as the Sheet formulas (Keen-or-later count, lowest `latest_price_minor`). Doctor probe "Workbook": ok when `XSOURCE_WORKBOOK_ID` is set and `tab_ids` returns the three fixed tabs; fix text "Run xsource workbook init and set XSOURCE_WORKBOOK_ID".

- [ ] **Step 1: Write the failing tests** — driving `board` with two open jobs and one closed one returns two rows, the job waiting on the operator first; an open job with no prices shows `—` for best price; the probe is `warn` with the fix when the id is unset and `ok` with no fix when set (fake client). In `tests/test_gareth_contracts.py` add `test_screen_pages_exist`: parse the "Cockpit pages (new)" table of `gareth-screens-v1.md`; assert `board` is a registered capability; assert `call_list` and `calls_to_file` are **not** yet registered, from a `_LATER_STAGES = {"call_list": 2, "calls_to_file": 2}` dict, so stage 2 has to remove them from the dict when it builds them; assert `contract.assert_render_model_parity(cockpit)` still passes.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** On Home, a job whose `waiting_on` starts with `You:` becomes a needs-you item `"<title>: <waiting_on minus 'You: '>"`, replacing the "Chase: …" wording for workbook jobs.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(cockpit): Board page and a workbook health check"`

### Task 10: Gareth's name and voice, and the town fix

**Files:**
- Create: `config/personas/gareth.toml`, `config/souls/gareth.md`
- Modify: `src/xsource/config.py` (default `operator_display_name` becomes `"Gareth"`; add `home_town: str | None` from `XSOURCE_HOME_TOWN`), `src/xsource/outreach/drafts.py`, `deploy/xsource-cloud-run.env.example` (add `XSOURCE_OPERATOR_DISPLAY_NAME=Gareth`, `XSOURCE_HOME_TOWN=`)
- Test: `tests/outreach/test_drafts.py`, `tests/test_persona.py`

**Interfaces:**
- Consumes: `clonway_cockpit.persona.load_persona`, `clonway_cockpit.persona_soul.load_soul` / `compose_system_prompt`.
- Produces: `gareth.toml` with `handle = "gareth"`, `name = "Gareth"`, `domain = "buying for the home — trades, servicing, contracts and renewals"`, `email = ""` (filled once the alias exists), `voice = "casual, friendly British; precise only on the job details"`. The soul states the anti-goals from the spec (never sends, never reads resident or family calls, never records a price without the operator's OK).

- [ ] **Step 1: Write the failing tests**

```python
def test_drafts_are_signed_with_the_configured_name(monkeypatch):
    monkeypatch.delenv("XSOURCE_OPERATOR_DISPLAY_NAME", raising=False)
    body = build_quote_request(_request(), _supplier()).body
    assert "Cheers,\nGareth" in body and "Milo" not in body

def test_prompt_names_the_configured_operator(): ...  # "Operator first name: Gareth"

def test_no_town_never_says_near_the_area(monkeypatch):
    monkeypatch.delenv("XSOURCE_HOME_TOWN", raising=False)
    body = build_quote_request(_request(town=None), _supplier()).body
    assert "near the area" not in body and "We're a local care home" in body

def test_home_town_is_used_when_triage_has_none(monkeypatch):
    monkeypatch.setenv("XSOURCE_HOME_TOWN", "Exampleton")
    assert "near Exampleton" in build_quote_request(_request(town=None), _supplier()).body

def test_gareth_persona_and_soul_load():
    assert load_persona(Path("config/personas/gareth.toml")).handle == "gareth"
    compose_system_prompt(load_soul(Path("config/souls/gareth.md")))  # raises if invalid
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** `_draft_context` falls back to `cfg.home_town`, then to the sentence "We're a local care home and we're after someone for a job." Replace both hard-coded "Milo" strings with `Config.from_env().operator_display_name`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(outreach): drafts signed by Gareth, and no more 'near the area'"`

### Task 11: Stage 1 finish — verify, walk through, hand over

**Files:**
- Modify: `README.md` (Runtime section: the workbook, `xsource workbook init|redraw|migrate`, new env vars), the spec's status line

- [ ] **Step 1: Run the full verification command** from Global Constraints → all green; record the output in the PR.
- [ ] **Step 2: Walk the cockpit key by key on a sandbox state dir** (fake workbook client or a scratch workbook the operator approves): Home shows the job's needs-you line; Board lists it; New request shows the shortlist before asking to create the tab.
- [ ] **Step 3: Write the operator's switch-over steps into the PR body**: run `xsource workbook init`, set `XSOURCE_WORKBOOK_ID` on the Cloud Run jobs, run `xsource workbook migrate` then `--apply`, then the deploy. Deploying needs the operator's go-ahead.
- [ ] **Step 4: `gh pr ready`, dispatch CI, merge under the merge gate.**
