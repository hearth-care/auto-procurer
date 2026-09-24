# The cockpit shows what the reply watcher is checking, and the health check gains three probes — Implementation Plan

Base: `origin/main` @ `5e8b6d3`. Size **S**. No wave. No dependencies.

## Goal

The office should be able to tell, from the procurement cockpit alone, whether supplier replies
are being picked up. Today the reply watcher (the scheduled job that reads Gmail threads for
supplier answers to our quote requests) keeps a record of when it last checked each open request,
but the only way to see it is to run `xsource watcher status` in a terminal. The cockpit card
called "Reply watcher" on shelf E is a placeholder that just tells you to run that command.

When this plan is built:

1. Opening shelf E, item 3 ("Reply watcher") lists the open requests the watcher is checking and
   when it last checked each one, the same rows the `xsource watcher status` command prints.
2. The health-check screen (the Doctor, opened with `G`) gains three probes: how many records the
   store holds, whether the reply watcher has gone stale, and how many signals (forward-looking
   items such as "chase this quote") the worker is currently raising for the fleet.

Nothing new is written anywhere. Both changes only read the request store that the cockpit
already loads.

Where this was decided: `docs/cockpit-journeys.md`, "Follow-up scoping" table, row 1
(`watcher.status`, "Cockpit card wired to live watcher state", size S, "Reuse `xsource watcher
status` data; card + model twin; no new logic") and row 3 (`doctor`, "Add store counts + watcher
+ signal count to probes", size XS, "Extend `doctor_build_probes`; no new screens or walks
required"). Ollie picked this as the Auto-Procurer candidate in the 23 September 2026 recovery
review.

## Architecture in a paragraph

The card becomes an ordinary read-only walk, built exactly like the existing "List requests" walk
(`_request_list_step` and `_request_list_handler` in `src/xsource/cli/cockpit.py`): one step that
loads the stores with `build_stores(Config.from_env())`, returns a `summary` and `rows`, and is
wrapped by the framework's `make_walk_handler`. The framework then produces the structured frames
agents read (the "model twin"), so no rendering code is written. To keep the card and the CLI
from ever disagreeing, one new function, `watcher_status_rows`, builds the rows, and the
`xsource watcher status` command in `src/xsource/cli/watcher.py` calls it instead of formatting
the rows itself. The CLI already imports from `xsource.cli.cockpit` (it borrows
`_AnthropicStructuredGateway`), so this adds no new dependency direction. The three Doctor probes
are appended to `doctor_build_probes` and reuse existing logic: the watcher-staleness rule is
`build_watcher_health_signals` from `src/xsource/signals/build.py` (stale when there are live
outreach threads and no open request was checked in the last 2 hours), and the signal count is
`len(build_xsource_signals(today=..., now=...))`, the same composed builder the nightly emitter
uses.

What the code does today, confirmed on `5e8b6d3`:

- `src/xsource/cli/cockpit.py:1285-1308` registers `watcher.status` inside a loop of three
  placeholder cards with `run=None`.
- `src/xsource/cli/watcher.py:155-162` (`status`) prints `open_requests=N` followed by one line
  per open request, `"<id> last_checked=<last_checked_at or ->"`, in store order. It prints
  nothing else. `docs/cockpit-journeys.md` section 5c claims it also prints thread count, backlog
  and heartbeat; it does not, and this plan works from what the code prints.
- `src/xsource/watcher/daemon.py:103-160` (`process_once`) visits every open request and stamps
  `request.watcher["last_checked_at"]`, so "the open requests the watcher is checking" is exactly
  the open requests.
- `src/xsource/cli/cockpit.py:1447-1503` (`doctor_build_probes`) returns six probes: Google Maps
  key, Anthropic key, Sheets token, Store, Budget, Home postcode.

## Global constraints

- **Implement on this branch.** Do not open a second pull request.
- **Read-only.** Neither the card nor the probes may write to any store, Sheet, Gmail or GCS
  object. The walk's blast radius is "Writes nothing." and a test proves it never calls
  `upsert`.
- **The `xsource watcher status` output must stay byte-for-byte identical.** Task 1 pins it
  before anything changes.
- **No new staleness rule.** The Reply watcher probe calls `build_watcher_health_signals`; do not
  copy its 2-hour threshold or its thread-counting into the cockpit.
- **Shelf order stays the same.** `tests/test_cockpit_placeholders.py::test_shelf_item_order_is_stable`
  must pass unchanged: shelf E is still `request.outreach`, `request.followup`, `watcher.status`.
- **Tests drive frames, never text.** Assert `ScreenModel` frames from `CockpitDriver`, step
  results, or probe objects. Never assert on `export_text()`.
- **Fake the clock.** Add a module-level `_utc_now()` seam in `cockpit.py` returning
  `dt.datetime.now(dt.UTC)`; the probes read the time through it and tests monkeypatch it.
- **Public repository.** Fixtures use invented ids (`r-0001`), invented thread ids (`t-1`) and no
  real supplier names or emails.
- **Gates**, from `CLAUDE.md` and `.github/workflows/ci.yml`, run exactly as written:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

## Task 1: Pin the `xsource watcher status` output, then share its rows

- [x] Add `test_watcher_status_prints_open_requests_and_last_check` to
      `tests/watcher/test_cli_run.py`. Seed a `JsonlStore(tmp_path / "requests.jsonl", Request)`
      with three requests: `r-0001` open with `watcher={"last_checked_at":
      "2026-09-23T09:58:00+00:00"}`, `r-0002` open with no watcher data, `r-0003` closed. Set
      `XSOURCE_STATE_DIR` to `tmp_path`, monkeypatch `xsource.cli.watcher.build_stores` to
      `lambda cfg: (object(), store, object())`, invoke `["watcher", "status"]` with `CliRunner`,
      and assert the exit code is 0 and `result.stdout` equals exactly
      `"open_requests=2\nr-0001 last_checked=2026-09-23T09:58:00+00:00\nr-0002 last_checked=-\n"`.
- [x] Run `uv run pytest -q tests/watcher/test_cli_run.py` and confirm it **passes on the
      unchanged code**. This is a characterisation pin: it records today's output so the next
      steps cannot change it.
- [x] Add `test_watcher_status_rows_matches_cli_lines` to `tests/walks/test_readonly_walks.py`:
      with the same three requests, `cockpit.watcher_status_rows(store.all())` returns
      `["r-0001 last_checked=2026-09-23T09:58:00+00:00", "r-0002 last_checked=-"]`.
- [x] Run `uv run pytest -q tests/walks/test_readonly_walks.py` and confirm it **fails** with an
      `AttributeError` for `watcher_status_rows`.
- [x] In `src/xsource/cli/cockpit.py`, add `watcher_status_rows(records) -> list[str]` near
      `_request_list_step`. It keeps store order, filters to `status == "open"`, and formats
      `f"{request.id} last_checked={request.watcher.get('last_checked_at', '-')}"`.
- [x] In `src/xsource/cli/watcher.py`, change `status()` to print `open_requests=N` and then the
      lines from `watcher_status_rows(requests.all())`, where `N` is the number of rows. Import it
      alongside the existing `_AnthropicStructuredGateway` import.
- [x] Run both test files again and confirm both pass.
- [x] Commit: `refactor(watcher): share the watcher status rows between CLI and cockpit`

## Task 2: Wire the Reply watcher card as a read-only walk

- [x] In `tests/walks/test_readonly_walks.py`, add:
      - `test_watcher_status_step_summary_and_rows`: with the Task 1 store monkeypatched into
        `cockpit_mod.build_stores`, `cockpit_mod._watcher_status_step(_ctx([]), {})` returns
        `ok=True`, `data["rows"]` equal to the two rows above, and `data["summary"]` equal to
        `"2 open request(s) watched · last check 2026-09-23T09:58:00+00:00"`. With no
        `last_checked_at` on any open request the summary ends `"· last check never"`. The latest
        check is the greatest `last_checked_at` string among open requests; ISO-8601 UTC strings
        written by `daemon._iso` sort correctly as text, so no date parsing is needed.
      - `test_watcher_status_walk_result_via_drive`: online stores as in
        `test_request_list_walk_result_via_drive`, then
        `CockpitDriver(host, keys=["E", "3", "y"]).run()`; the first `walk.result` frame has
        `meta["ok"] is True` and `meta["message"]` equal to the summary above.
      - `test_watcher_status_walk_never_writes`: wrap the request store in `_NoWriteStore` and
        run `_watcher_status_step`; it returns `ok=True` without raising.
- [x] In `tests/test_cockpit_placeholders.py`, remove `"watcher.status"` from
      `_PLACEHOLDER_STATUS_MARKERS` and delete `test_watcher_status_card_summary_via_drive`. That
      test asserts the card says "Read-only via CLI:", which is the placeholder wording this plan
      retires; the drive test above replaces it.
- [x] In `tests/cli/test_equivalent_cli_parity.py`, add `"watcher.status"` to the parametrize list
      of `test_wired_walk_preflight_cli_matches_registry` (currently four keys: `request.list`,
      `book.search`, `book.import`, `book.publish`).
- [x] Run `uv run pytest -q tests/walks/test_readonly_walks.py tests/test_cockpit_placeholders.py tests/cli/test_equivalent_cli_parity.py`
      and confirm the three new walk tests and the new parity case **fail**.
- [x] In `src/xsource/cli/cockpit.py`:
      - add `_CLI_WATCHER_STATUS = "xsource watcher status"` beside `_CLI_REQUEST_LIST`, and
        `_WATCHER_STATUS_BLAST = BlastRadius(summary="Writes nothing.", reversible="No write is
        performed.")` beside `_REQUEST_LIST_BLAST`;
      - add `_watcher_status_step(ctx, bag)` returning `StepResult(ok=True, data={"summary": ...,
        "rows": watcher_status_rows(records)})`, appending `_quarantine_suffix(requests_)` to the
        summary as `_request_list_step` does;
      - add `_watcher_status_handler = make_walk_handler(title="Reply watcher", steps=[Step(label="Status",
        run=_watcher_status_step)], blast_radius=_WATCHER_STATUS_BLAST,
        preconditions_fn=_readonly_preconditions, equivalent_cli=_CLI_WATCHER_STATUS, total=2)`;
      - in `register_all`, remove the `watcher.status` tuple from the placeholder loop and register
        it on its own immediately after that loop, with `shelf="E"`, `title="Reply watcher"`,
        `summary="Show which open requests the reply watcher is checking and when it last checked
        each. Read-only."`, `equivalent_cli=_CLI_WATCHER_STATUS`, `run=_watcher_status_handler`,
        `blast_radius=_WATCHER_STATUS_BLAST`, `money_movement=False`.
- [x] Run the same three test files and confirm they pass, including
      `test_shelf_item_order_is_stable` unchanged.
- [x] Commit: `feat(cockpit): wire the Reply watcher card to live watcher state`

## Task 3: Three new Doctor probes

- [x] Create `tests/test_doctor_probes.py`. Build the report dict that `doctor_build_report`
      returns by hand: `cfg` from `Config.from_env()` with `XSOURCE_STATE_DIR` set to `tmp_path`,
      three `JsonlStore` objects marked online (`store.offline = False`), and a small stub budget
      whose `level()` returns `"ok"` and `spent()` returns `0.0`. Monkeypatch `cockpit._utc_now`
      to `2026-09-23T12:00:00+00:00` and `cockpit.build_xsource_signals` to a stub. Tests:
      - `test_doctor_probe_names_in_order`: the probe names are the six existing ones followed by
        `"Store records"`, `"Reply watcher"`, `"Pending signals"`.
      - `test_store_records_probe_counts`: one supplier, three requests and no invoices give level
        `"ok"` and detail `"1 supplier(s) · 3 request(s) · 0 invoice(s)"`; with `requests` set to
        `None` the level is `"warn"` and the detail is `"store unavailable"`.
      - `test_reply_watcher_probe_stale`: an open request whose shortlist entry has
        `outreach={"thread_id": "t-1"}` and whose `last_checked_at` is `2026-09-23T09:00:00+00:00`
        (3 hours old) gives level `"error"` and detail
        `"1 live outreach thread(s), watcher stale."`, the detail of the signal
        `build_watcher_health_signals` raises.
      - `test_reply_watcher_probe_fresh`: the same request checked at `11:30` gives level `"ok"`
        and detail `"fresh · 1 open request(s) watched"`.
      - `test_reply_watcher_probe_nothing_to_watch`: no outreach threads gives level `"ok"` and
        detail `"no live outreach threads"`.
      - `test_pending_signals_probe`: the stub returning two signals gives level `"warn"` and
        detail `"2 raised · not sent (XSOURCE_EMIT_SIGNALS off)"`; returning none gives level
        `"ok"` and detail starting `"0 raised"`; with `XSOURCE_EMIT_SIGNALS=1` the detail ends
        `"· sent to the fleet"`.
      - `test_doctor_frame_lists_new_probes_via_drive`: monkeypatch `cockpit.build_stores` and
        `cockpit.build_budget` so `_status()` returns the fixture, drive
        `CockpitDriver(cockpit._host(agent_mode=True), keys=["G", "q"]).run()`, take the frame
        with `kind == "doctor"`, and assert its `probes` region has rows for the three new probe
        names. Read `clonway_cockpit.render.model_doctor` for the row fields before writing the
        assertion.
- [x] Run `uv run pytest -q tests/test_doctor_probes.py` and confirm it **fails**.
- [x] In `src/xsource/cli/cockpit.py`:
      - add `_utc_now()`;
      - import `build_watcher_health_signals` and `build_xsource_signals` from
        `xsource.signals.build` (the module is already loaded through `xsource.signals.emit`, so
        there is no import cycle);
      - append three `Probe`s to the list `doctor_build_probes` returns, after "Home postcode",
        each with `fix=None`:
        - "Store records": counts from `suppliers.all()`, `requests_.all()` and `invoices.all()`;
          `"warn"` / `"store unavailable"` when any of the three is `None`.
        - "Reply watcher": call `build_watcher_health_signals(request_records, today=now.date(),
          now=now)`; a returned signal gives `"error"` with that signal's `detail`; otherwise
          `"ok"`, with `"no live outreach threads"` when no open request has an outreach
          `thread_id`, else `"fresh · N open request(s) watched"`. `"warn"` / `"store unavailable"`
          when `requests_` is `None`.
        - "Pending signals": `n = len(build_xsource_signals(today=now.date(), now=now))`; level
          `"warn"` when `n` is above 0, else `"ok"`; detail `f"{n} raised · "` followed by
          `"sent to the fleet"` when `signals_emit._enabled()` is true, else
          `"not sent (XSOURCE_EMIT_SIGNALS off)"`.
- [x] Run `uv run pytest -q tests/test_doctor_probes.py` and confirm it passes.
- [x] Commit: `feat(doctor): add store record, reply watcher and pending signal probes`

## Task 4: Update the operator documents

- [x] In `docs/cockpit-journeys.md`: rewrite section 5c to say the card is live, list what it
      shows, and remove the incorrect claim about thread count, backlog and heartbeat; add the
      three probes to section 6a; mark follow-up rows 1 and 3 as built, naming this plan.
- [x] In `README.md`: change the shelf G row (line 63) to "Doctor probes: config, credentials,
      store, budget, store record counts, reply watcher, pending signals", and the
      `xsource watcher status` comment (line 30) to "open requests and when the watcher last
      checked each".
- [x] Commit: `docs: record the live Reply watcher card and new Doctor probes`

## Task 5: Full gates

- [ ] Run each gate and paste the real output into `## HANDOFF NOTES`:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

- [ ] Confirm `tests/test_no_send_endpoints.py` passed within the full run (the draft-never-send
      gate).
- [ ] `git diff origin/main --stat` names only the files in the fence below.
- [ ] Commit: `docs(plan): record gate results`

## Implementation fence

This pull request will create or modify exactly these production files:

- Modify `src/xsource/cli/cockpit.py` — `watcher_status_rows`, the Reply watcher walk and its
  registration, `_utc_now`, and three Doctor probes (Tasks 1 to 3).
- Modify `src/xsource/cli/watcher.py` — `status()` prints rows from `watcher_status_rows` (Task 1).

Tests this pull request will create or modify:

- Modify `tests/watcher/test_cli_run.py` — the CLI output pin (Task 1).
- Modify `tests/walks/test_readonly_walks.py` — row helper, step, drive and no-write tests
  (Tasks 1 and 2).
- Modify `tests/test_cockpit_placeholders.py` — retire the placeholder marker and test (Task 2).
- Modify `tests/cli/test_equivalent_cli_parity.py` — add `watcher.status` to the wired-walk
  parity list (Task 2).
- Create `tests/test_doctor_probes.py` — the three probes (Task 3).

Documents this pull request will change, which are not implementation files:

- Modify `docs/superpowers/plans/2026-09-23-watcher-status-card.md` — this plan's checkboxes and
  `## HANDOFF NOTES`.
- Modify `docs/cockpit-journeys.md` — sections 5c, 6a and the follow-up table (Task 4).
- Modify `README.md` — shelf G row and the watcher status comment (Task 4).

**No other implementation file may change.** If a task needs a production file not listed here,
stop and record why in `## HANDOFF NOTES` rather than widening this fence.

## Out of scope, and left switched off

- Signal emission stays as it is. `XSOURCE_EMIT_SIGNALS` defaults off and only Ollie turns it on;
  the new probe reports whether it is on and changes nothing.
- No GCS heartbeat read. The watcher writes `heartbeats/xsource.watcher/latest.json` to the fleet
  bucket, but reading it would add a new storage read to the cockpit. The staleness probe uses
  the request store's `last_checked_at`, which the fleet's watcher-stale signal already relies on.
- No new credentials, scopes or Cloud Run changes. The nightly jobs are untouched.
- The Sheet sync preview (follow-up row 2) and the Checkatrade partner-lead walk (row 4, which
  needs Ollie's data-processing sign-off) are separate work.

Dispatch-ready.

Artifacts:
- `docs/superpowers/plans/2026-09-23-watcher-status-card.md`

Routing: builder implements on this branch (`claude/plan-watcher-status-card`), then independent QA.
Plan signal: Size S, 2 production files, read-only change, no dependencies, no wave.
Gates planned: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest -q`.

## RUNBOOK DELTA

Operator-facing: yes. Office staff see a working Reply watcher card and three more Doctor lines.

- Shelf E, item 3 "Reply watcher" now opens a read-only screen listing each open request with the
  time the watcher last checked it, and a summary of how many are watched and the latest check.
  It is the same information as `xsource watcher status`.
- The Doctor (`G`) shows "Store records", "Reply watcher" and "Pending signals". A red "Reply
  watcher" line means outreach threads are live but no open request has been checked for more
  than 2 hours: check the watcher job and its logs to establish the cause. "Pending signals" in amber is
  normal when there is follow-up work; it counts items, it does not mean anything is broken.
- No new command, flag, environment variable or sign-off.

## HANDOFF NOTES

- Base commit: `5e8b6d3`.
- Status: Tasks 1–4 complete; next run full gates and final review.
- Task 1: CLI characterisation passed unchanged (2 passed); helper test failed with the expected AttributeError; shared implementation passed both files (13 passed).
- Pre-flight: Tasks 1 and 2 share ordered string rows; Task 3 reuses existing signal builders. No interface conflicts or dependencies.
- Storage: verified approved external volume; environment and caches external, expected growth below 1 GiB. No diagnostic copies.
- Known failing tests: none.
- [ASSUMPTION] "Pending signal count" in `docs/cockpit-journeys.md` means the number of signals
  the worker's horizon scan currently raises (`build_xsource_signals`), since xsource keeps no
  queue of unsent signals. If the builder finds a stored queue, record it here and ask before
  changing the definition.

- Task 2: five expected failures before implementation; 35 passed after wiring the card. Empty/quarantined stores also covered; shelf order test unchanged.

- Task 3: missing probes failed before implementation; 16 passed after implementation. Includes exact two-hour boundary, never checked, closed threads, missing stores and emission on/off.
- Ruling: enabled signals say "emission enabled", replacing the planned "sent to the fleet". The flag proves configuration only; the existing emitter explicitly swallows delivery failures. Claiming delivery would mislead operators.

- Task 4: operator guidance updated and reviewed against the implementation. Corrected prior claims about thread counts, backlog, heartbeat and the status command needing Gmail credentials. Existing store-loading cache/quarantine effects are documented; the new logic never upserts or emits.
