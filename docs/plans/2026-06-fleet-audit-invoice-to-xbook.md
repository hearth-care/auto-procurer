# [Plan] Invoice capture → xbook AP handoff

**Status:** implemented on PR #13; awaiting operator QA
**Source:** fleet audit 2026-06-11, items S5, S6
**Wave:** 2 (S5), 3 (S6)

The audit's headline finding on this worker: the procurement→books chain — the
whole point of an auto-procurer in a fleet that also has an auto-bookkeeper —
is broken at the handoff. xsource finds suppliers, drafts outreach, parses
quotes, and records a chosen supplier; then the trail goes cold. The invoice
that inevitably follows is invisible to this worker and to the books worker.
This plan specifies the invoice record (S5) and the `payment.required` signal
contract that hands it to the books worker's AP intake (S6).

## Why

Every claim was re-verified against `origin/main` (`ebfd22a`) on 2026-06-11.

- **The request lifecycle ends at "chosen", not "paid".**
  `src/xsource/sheet/sync.py:80` — when the operator marks a supplier chosen in
  the request Sheet, the nightly sync sets `request.status = "closed"`. The
  quote lands in `Supplier.price_history` with outcome `"used"`
  (`sync.py:60-70`). Nothing models the invoice, the amount actually charged,
  or whether it was ever paid.
- **The schema seams for linkage already exist.**
  `src/xsource/store/models.py:75` — `Request.chosen_supplier_id`;
  `models.py:34` — `Supplier.price_history` (rows of
  `{request_id, date, amount, outcome}`). An invoice record can anchor to both
  without restructuring the store.
- **xsource emits only three signal kinds, none about money owed.**
  `src/xsource/signals/build.py` — `action.required` chase-quotes (line 117),
  `deadline.approaching` recurring service (line 151), `anomaly.detected`
  watcher health (line 193). There is no payment- or invoice-shaped signal.
- **Nobody downstream consumes worker signals anyway (yet).** Fleet-wide
  (audit §4.3), every worker writes to the shared signal store and only the
  orchestrator reads it, for dashboarding. A procurement→books handoff is the
  first true worker→worker signal flow, which is why the *contract* (wire
  shape, idempotency, lifecycle, error path) is most of this plan.
- **Store and importer precedents exist.** `src/xsource/store/remote.py` —
  `SyncedStore` (local JSONL + GCS blob sync); `src/xsource/book/importer.py`
  — CSV seed import. An invoice store and importer follow the same patterns.

## Scope

In scope:

- `InvoiceRecord` schema + `invoices.jsonl` synced store (S5)
- capture paths: manual CLI/walk entry and CSV import (S5)
- price-history linkage and quote-vs-invoice variance flag (S5)
- the `payment.required` signal contract: wire schema, idempotency keys,
  status lifecycle, error/return path (S6)
- emission + acknowledgement-ingestion logic on the xsource side (S6)

Out of scope (explicitly):

- **the xbook-side AP intake consumer — cross-repo dependency**, tracked in the
  books worker's repo; this plan ships the contract and fixtures it will
  consume
- email/attachment invoice ingestion (OCR/PDF parsing) — a later capture path;
  the schema reserves a `source` field for it
- any payment *execution* — the fleet posture is draft/propose only; money
  movement stays with the operator and the books worker's own gates

## Spec

### InvoiceRecord (S5)

New dataclass in `src/xsource/store/models.py`, persisted via a third
`SyncedStore` (`invoices.jsonl`) built in `src/xsource/wiring.py:build_stores`
alongside suppliers/requests:

| Field | Type | Notes |
|---|---|---|
| `id` | str | store-issued (`i-XXXX` via `next_id("i")`) |
| `request_id` | str | links to `Request.id`; may be empty for ad-hoc invoices |
| `supplier_id` | str | links to `Supplier.id` |
| `amount_minor` | int | pence; avoids float money |
| `currency` | str | default `"GBP"` |
| `invoice_number` | str \| None | supplier's reference |
| `invoice_date` | str (ISO date) | |
| `due_date` | str \| None (ISO date) | drives signal `due_at` |
| `description` | str | what it's for, operator-readable |
| `source` | str | `"manual"` \| `"csv"` (later: `"email"`) |
| `file_ref` | str \| None | pointer to a stored copy (Drive/GCS), no binary in the store |
| `status` | str | lifecycle below |
| `handoff` | dict | emission/ack bookkeeping (timestamps, ack ref, attempt count) |
| `created_at` / `updated_at` | str (ISO datetime) | |

Status lifecycle (single source of truth, validated on transition):

```
captured → emitted → acknowledged → settled
              │            │
              │            └→ disputed → (re-emitted | settled | written_off)
              └→ rejected (consumer refused; needs operator fix → re-emit)
```

Linkage rules on capture:

- if `request_id` is set and the request has a `chosen_supplier_id`, warn when
  it differs from the invoice's `supplier_id` (caught a mis-keyed invoice);
- append a `price_history` row with outcome `"invoiced"` and the actual amount;
- when the invoiced amount deviates from the recorded quote beyond a
  configurable tolerance (default 10%), flag a variance warning in the capture
  report and an `action.required` signal — quoted-vs-billed drift is precisely
  the intelligence a procurement worker should accumulate.

### Importer + capture surfaces (S5)

- `xsource invoice add` — interactive/flagged CLI capture of a single invoice.
- `xsource invoice import <csv>` — CSV import mirroring
  `book/importer.py` conventions (header-keyed, idempotent on
  `(supplier_id, invoice_number)`, returns `{imported, skipped}`).
- Cockpit: an `invoice.capture` capability (walk: pick request → enter details
  → review → confirm-apply) and an invoices pill (count of `captured` +
  `rejected` needing attention). Both go through the existing walk/confirm
  machinery; no new write paths outside the gate.

### `payment.required` signal contract (S6)

Transport: the existing per-worker signal store (the shared fleet bucket path
the framework's emit helper already writes; see `src/xsource/signals/emit.py`).
No new infrastructure — the consumer polls or subscribes the same way the
orchestrator does today.

Wire shape — one signal per invoice in the `payment.required` state, emitted by
a new builder in `src/xsource/signals/build.py` and composed into the existing
horizon scan:

| Signal field | Value |
|---|---|
| `worker` | `"xsource"` |
| `kind` | `"payment.required"` |
| `title` | `Invoice <invoice_number or id> — <supplier name>` |
| `detail` | amount + currency + short description |
| `level` / `urgency` | `warn`/`normal`; `error`/`high` when overdue |
| `due_at` | invoice `due_date` |
| `dedup_key` | `xsource\|invoice\|<invoice id>` — **the idempotency key** |
| `source_id` / `source_ref` | invoice id — consumer fetches the full record |

Contract rules:

1. **Idempotency:** `dedup_key` is stable for the life of the invoice. The
   builder re-emits on every scan until the invoice leaves the emittable
   states, so a missed scan is self-healing; the consumer must treat repeated
   `dedup_key`s as the same obligation (consumer-side dedup, as the fleet
   already does for daily signals).
2. **Full record stays in the store, not the wire.** The signal model is
   deliberately thin (no structured payload field at the pinned framework rev);
   the consumer reads the invoice record from the shared state path by
   `source_id`. This avoids forking the fleet wire shape — extending the
   framework `Signal` with a payload dict is noted as an alternative requiring
   a framework change.
3. **Acknowledgement path:** the consumer writes an ack record (invoice id,
   consumer run id, disposition `accepted | rejected:<reason>`, timestamp) to
   an agreed handshake location in the shared store. xsource's nightly sync
   ingests acks: `emitted → acknowledged` or `emitted → rejected` (+ an
   `action.required` signal telling the operator what to fix).
4. **Error/return path:** `rejected` invoices stay visible (pill + signal)
   until the operator edits and re-emits, or marks `written_off`. `disputed`
   is reserved for the books side signalling a mismatch after acceptance.
5. **Versioning:** the handshake record carries a `contract_version` (start at
   `1`); breaking changes bump it and the consumer ignores versions it doesn't
   know.

### Cross-repo dependency (S6)

The books-worker AP intake (consuming `payment.required`, writing acks,
surfacing draft AP entries to its operator) is **out of scope here and tracked
in that repo**. This plan ships, as the contract artifact: a markdown contract
doc (`docs/contracts/payment-required-v1.md`) plus JSONL fixtures
(`tests/contracts/fixtures/`) that both repos' tests consume, so the two sides
can't drift silently.

## Implementation plan

### Phase 1 — schema + store (Wave 2, S)

- [x] `src/xsource/store/models.py`: `InvoiceRecord` dataclass + lifecycle
      transition validator.
- [x] `src/xsource/wiring.py`: third `SyncedStore` for `invoices.jsonl`.
- [x] `tests/store/test_models.py` additions: round-trip, transition table
      (legal/illegal moves), money-as-minor-units.

### Phase 2 — capture + linkage (Wave 2, M)

- [x] `src/xsource/invoices/capture.py`: capture/import logic, price-history
      append, variance check.
- [x] `src/xsource/cli/invoice.py`: `invoice add`, `invoice import`,
      `invoice list`.
- [x] Cockpit: `invoice.capture` capability + invoices pill in
      `capture_state` (render/model parity suite must stay green).
- [x] Tests: importer idempotency, chosen-supplier mismatch warning, variance
      flag at the tolerance boundary, pill counts.

### Phase 3 — signal emission + ack ingestion (Wave 3, M)

- [x] `src/xsource/signals/build.py`: `build_payment_required_signals` composed
      into the horizon scan; overdue escalation.
- [x] Handshake ack reader wired into the nightly sync path
      (`src/xsource/cli/request.py` sync-all or a sibling `invoice sync`).
- [x] Tests: emission only in emittable states; stable dedup keys; ack
      transitions; rejected-invoice operator signal.

### Phase 4 — contract artifact (Wave 3, S)

- [x] `docs/contracts/payment-required-v1.md`: the contract above, frozen.
- [x] Shared fixtures: a golden `latest.jsonl` slice + ack records; a contract
      test that validates the emitter's output against the fixtures.
- [ ] Hand the fixture set to the books-worker repo (cross-repo PR, tracked
      there). Deferred by dispatch rule for PR #13: stay on this PR, never open
      another PR. The in-repo fixture set is ready for the books-worker consumer.

## Acceptance criteria

- [x] An invoice can be captured (CLI and walk), linked to its request and
      supplier, and survives a store round-trip.
- [x] Capturing an invoice against a chosen supplier appends an `"invoiced"`
      price-history row; a >tolerance quote-vs-invoice gap raises a variance
      flag and a signal.
- [x] Every unsettled, emittable invoice produces exactly one
      `payment.required` signal per scan with a stable `dedup_key`; settled and
      acknowledged invoices produce none.
- [x] A consumer ack flips the invoice state; a rejection becomes an
      operator-visible `action.required` item.
- [x] The contract doc + fixtures exist and the emitter is tested against them.
- [x] No new write path bypasses the cockpit gate; the worker still never sends
      email or moves money (`tests/test_no_send_endpoints.py`,
      `tests/test_safety.py` untouched and green).

## Risks & dependencies

- **Cross-repo coupling (the big one):** the chain only closes when the books
  worker ships its consumer. Mitigation: the contract doc + fixtures are the
  deliverable boundary; xsource-side work is fully testable against them.
- **Thin wire shape:** squeezing data into `detail`/`source_ref` is deliberate
  but means the consumer must read the shared store; if that proves awkward, a
  framework `Signal` payload extension is the fallback (framework change,
  coordinate via the framework repo).
- **Signal title→kind mapping:** the framework currently maps titles to kinds
  internally for dedup; a new `payment.required` kind must be verified against
  the pinned framework rev before relying on dedup behaviour (known audit
  finding on the framework side).
- **Store growth:** invoices accumulate forever in a JSONL store; fine at this
  scale, but note a future archival cutoff.
- **Operator workload:** manual capture is a stopgap; if it doesn't get used,
  the email-ingestion capture path moves up the priority list.

## Next-agent pickup

1. Branch off `main`; do not stack on this planning branch.
2. Re-verify the file:line citations against current `main` first (this repo
   moved during the audit itself).
3. Phases 1–2 are self-contained in this repo and shippable as one or two PRs;
   Phase 3 needs the handshake location agreed (propose it in the contract doc
   PR and get operator sign-off); Phase 4's cross-repo fixture handoff happens
   in the books worker's repo, not here.
4. Run `uv run pytest -q`, `uv run ruff check .`, `uv run mypy` before each PR.
5. Public repo: keep bucket names, project ids, and real supplier details out
   of docs, fixtures, and tests — use the constants in `wiring.py`/`emit.py`
   and invented fixture data.

## HANDOFF NOTES

- Current phase: QA fix for qa-codex-20260612T065532Z-7032 full gates complete on
  latest `origin/main`; finish protocol.
- Completed: Phase 1 schema/store slice with `InvoiceRecord`, lifecycle validation,
  `invoices.jsonl` `SyncedStore`, and focused tests.
- Completed: Phase 2 capture/import/CLI/cockpit slice with price-history linkage,
  supplier mismatch warnings, variance detection, idempotent CSV import, root
  `xsource invoice` commands, `invoice.capture`, and the invoices attention pill.
- Completed: Phase 3 signal/ack slice with `payment.required`, overdue escalation,
  rejected-invoice `action.required`, `xsource invoice sync-acks`, and ack transitions.
- Completed: Phase 4 in-repo contract artifact with
  `docs/contracts/payment-required-v1.md`, `tests/contracts/fixtures/latest.jsonl`,
  `tests/contracts/fixtures/acks.jsonl`, and a fixture-backed contract test.
- QA fix (fixer-claude-20260611T213208Z-55255): Fixed critical lifecycle bug where
  ack ingestion silently skipped all acks because invoices stay `captured` but
  `transition_to("acknowledged")` requires `emitted`. Fix: `acks.py` now auto-advances
  `captured → emitted` before processing the disposition — the ack proves the signal
  reached the consumer, so advancing through `emitted` is correct. Also updated
  `test_acks.py` to exercise the real `capture_invoice() → ingest_ack_records` path
  instead of constructing invoices in `emitted` state directly, which was masking the bug.
- QA fix (fixer-codex-20260611T214518Z-55255): Added the missing real horizon path for
  invoice variance `action.required` signals. Variance metadata already persists on
  `InvoiceRecord.handoff["variance"]`; `build_invoice_variance_signals` now derives a stable
  `xsource|invoice-variance|<invoice id>` signal from captured invoice state and the composed
  horizon scan includes it. The signal is suppressed when `handoff["variance_resolved_at"]`
  exists or the invoice is terminal (`settled` / `written_off`).
- Verification: focused GREEN
  `uv run pytest tests/test_signals_build.py::test_invoice_variance_signal_uses_captured_invoice_state -q`
  returned `1 passed in 0.01s`.
- Verification: nearby regression suite
  `uv run pytest tests/test_signals_build.py tests/invoices/test_capture.py -q`
  returned `18 passed in 6.15s`.
- Verification: full suite `uv run pytest -q` returned `179 passed in 16.06s`.
- Verification: `uv run ruff check .` returned `All checks passed!`.
- Verification: `uv run mypy` returned `Success: no issues found in 57 source files`.
- Verification: `pre-commit run --all-files` returned `InvalidConfigError:
  .pre-commit-config.yaml is not a file`.
- Rebase note (2026-06-11): rebased onto latest `origin/main`; preserved mainline
  request-sync `run_session`/heartbeat changes while keeping the PR's three-store
  `(suppliers, requests, invoices)` wiring. Preserved mainline cockpit pending-reply/store
  tests while keeping invoice capture/pill coverage.
- Rebase drift fix: mainline added `Config.fleet_bucket` and `Config.state_prefix`; invoice
  store wiring now uses `state_blob(cfg, "invoices.jsonl")`, and tests pass explicit
  config values.
- Verification: rebase-focused failures
  `uv run pytest tests/store/test_remote.py::test_build_stores_includes_invoice_store tests/test_cockpit_render.py::test_capture_state_counts_invoices_needing_attention -q`
  returned `2 passed in 0.06s`.
- Verification: post-rebase full suite `uv run pytest -q` returned `195 passed in 3.74s`.
- Verification: post-rebase `uv run ruff check .` returned `All checks passed!`.
- Verification: post-rebase `uv run mypy` returned
  `Success: no issues found in 59 source files`.
- Verification: post-rebase `pre-commit run --all-files` returned `InvalidConfigError:
  .pre-commit-config.yaml is not a file`.
- Verification: post-QA-fix `uv run pytest -q` returned `178 passed in 21.98s`.
- Verification: `uv run ruff check .` returned `All checks passed!`.
- Verification: `uv run mypy` returned `Success: no issues found in 57 source files`.
- Decisions: `build_stores` now returns `(suppliers, requests, invoices)`; existing callers
  ignore the invoice store until their phase uses it.
- Decisions: invoice capture stores money as `amount_minor`; variance checks normalise older
  supplier quote rows with `amount` by treating them as pounds.
- Decisions: ack ingestion is a sibling nightly command, `xsource invoice sync-acks`,
  defaulting to `XSOURCE_STATE_DIR/payment-required-acks.jsonl`; this satisfies the
  plan's "request sync-all or sibling invoice sync" option without mixing invoice handoff into
  Sheet request sync.
- Deviation (original builder): signal builders stay pure; they do not mutate invoice
  status. Ack ingestion owns lifecycle transitions including the implicit `captured→emitted`
  advance on first ack receipt.
- Deferred: cross-repo fixture handoff to the books-worker repo, because this dispatch
  explicitly forbids opening another PR. The fixture set exists in this PR.
- Known-failing tests: none. Focused RED was
  `uv run pytest tests/test_signals_build.py::test_invoice_variance_signal_uses_captured_invoice_state -q`,
  which failed because `build_invoice_variance_signals` did not exist.
- QA fix (fixer-claude-20260612T055026Z-89007): Added ISO date validation to
  `capture_invoice` for `invoice_date` and `due_date`; malformed dates (e.g. UK format
  `11/06/2026`) now raise `ValueError` before any store write. Fixed `import_csv` to
  require `amount_minor` column presence and a positive integer value; missing/zero amounts
  are counted as `errored` rows and not persisted. `import_csv` now returns
  `{"imported": ..., "skipped": ..., "errored": ...}`. Per-row `ValueError` from
  `capture_invoice` (e.g. bad dates in CSV) is caught and counted as errored. Six new
  tests cover: malformed invoice_date rejection, malformed due_date rejection, missing
  amount_minor column, zero amount_minor, and malformed date in CSV import.
- Verification: `uv run pytest -q` returned `200 passed in 6.67s`.
- Verification: `uv run ruff check .` returned `All checks passed!`.
- Verification: `uv run mypy` returned `Success: no issues found in 59 source files`.
- QA fix (fixer-claude-20260612T060714Z-7032): Fixed non-positive amount bypass (Finding 1):
  `capture_invoice` now raises `ValueError` for `amount_minor <= 0` before any store write,
  centralising the guard so CLI, cockpit, and CSV import all share the same invariant.
  The cockpit `_invoice_details_step` now validates `int(amount_text)` with try/except and
  a `<= 0` check, returning a clean `StepResult(ok=False)` instead of raising uncaught
  `ValueError`. Fixed blank invoice_number CSV idempotency bug (Finding 2): `import_csv` now
  errors rows with a blank `invoice_number` instead of importing them without an idempotency
  key, which previously created duplicate invoices on every rerun. Added 7 regression tests:
  `capture_invoice` rejects zero/negative amounts (no persist); blank invoice_number in CSV
  errors (no persist, two reruns produce two errored counts, no duplicate); cockpit step returns
  clean `StepResult` for non-numeric, zero, and negative amounts, and accepts valid amount.
- Verification: `uv run pytest -q` returned `207 passed in 5.86s`.
- Verification: `uv run ruff check .` returned `All checks passed!`.
- Verification: `uv run mypy` returned `Success: no issues found in 59 source files`.
- QA fix (fixer-claude-20260612T061815Z-7032): Addressed the two HIGH findings from
  qa-codex-20260612T061246Z-7032.
  - Finding 1 (rejected-invoice recovery path was dead): added `reemit_invoice` and
    `write_off_invoice` to `src/xsource/invoices/capture.py`, exposed as `xsource invoice reemit
    <id>` (rejected → emitted, with optional `--amount-minor/--invoice-date/--due-date/
    --description/--invoice-number` corrections, validated like capture; clears the rejection
    reason) and `xsource invoice write-off <id>` (rejected → written_off). Added
    `rejected → written_off` to the `InvoiceRecord` transition table. The rejected-invoice
    `action.required` signal detail now names both commands so the CTA points at a real
    workflow. Contract doc updated. `tests/invoices/test_recovery.py` drives the full
    rejected → corrected → re-emitted → acknowledged path end to end plus write-off and guard cases.
  - Finding 2 (malformed ack `contract_version` crashed sync-acks): `ingest_ack_records` now
    parses the version via `_is_supported_version`, counting non-integer or unsupported
    versions as `skipped` and continuing past them. Three new tests in `tests/invoices/test_acks.py`
    cover non-integer, unsupported-numeric, and continue-past-bad-row cases.
- Verification (post-fix, pre-rebase): `uv run pytest -q` returned `218 passed`.
- Rebase (2026-06-12, fixer-claude-20260612T061815Z-7032): rebased onto latest origin/main,
  which now has PR #14 (p4-completion) merged. Resolved additive conflicts in
  `src/xsource/cli/cockpit.py` (main added `request.trigger`/`request.followup`/`request.reorder`
  walks + capabilities; PR added the invoice walk + `invoice.capture` capability — kept both) and
  `tests/cli/test_runtime_commands.py` (kept both the reorder-rejects and invoice-registered tests).
  Drift fix: main's p4 callers (`request.followup`/`reorder` in `cockpit.py` and `cli/request.py`)
  unpacked a 2-tuple from `build_stores`, but this branch returns the 3-tuple
  `(suppliers, requests, invoices)`; updated all callers and the matching test fakes to the 3-tuple
  contract. Main also added a required `Config.operator_display_name`; added it to the two literal
  `Config(...)` builds in `tests/test_cockpit_render.py` and `tests/store/test_remote.py`.
- Verification (post-rebase): `uv run pytest -q` returned `257 passed in 3.85s`;
  `uv run ruff check .` returned `All checks passed!`; `uv run mypy` returned
  `Success: no issues found in 60 source files`. `pre-commit` is unavailable (no
  `.pre-commit-config.yaml` in this repo — expected, confirmed across prior QA rounds).
- QA fix (fixer-codex-20260612T064500Z-7032): Addressed the two HIGH findings from
  qa-codex-20260612T063408Z-7032.
  - Finding 1 (malformed ack JSONL crashed `sync-acks`): `read_ack_jsonl` now parses
    line-by-line, converts malformed/non-object rows into skipped sentinel records, and
    lets later valid ack rows continue into `ingest_ack_records`.
  - Finding 2 (`reemit --amount-minor` left stale derived state): amount corrections now
    require supplier-store context, update the linked `"invoiced"` price-history row,
    recompute or clear `handoff["variance"]`, set `variance_resolved_at` when a previous
    variance is resolved, and then re-emit the invoice. The CLI passes suppliers through.
- Verification: focused RED
  `uv run pytest tests/invoices/test_acks.py::test_read_ack_jsonl_continues_past_malformed_lines tests/invoices/test_recovery.py::test_reemit_amount_correction_updates_variance_and_price_history -q`
  returned two failures: `JSONDecodeError` in `read_ack_jsonl`, and
  `TypeError: reemit_invoice() got an unexpected keyword argument 'suppliers'`.
- Verification: focused GREEN
  `uv run pytest tests/invoices/test_acks.py::test_read_ack_jsonl_continues_past_malformed_lines tests/invoices/test_recovery.py::test_reemit_amount_correction_updates_variance_and_price_history -q`
  returned `2 passed in 0.03s`.
- Verification: nearby regression suite
  `uv run pytest tests/invoices/test_acks.py tests/invoices/test_recovery.py tests/invoices/test_capture.py tests/test_signals_build.py -q`
  returned `42 passed in 0.07s`.
- Rebase check: `git fetch origin && git rebase origin/main` returned
  `Current branch claude/plan-invoice-to-xbook is up to date.`
- Verification: full suite `uv run pytest -q` returned `259 passed in 9.72s`.
- Verification: `uv run ruff check .` returned `All checks passed!`.
- Verification: `uv run mypy` returned `Success: no issues found in 60 source files`.
- Verification: `pre-commit run --all-files` returned `InvalidConfigError:
  .pre-commit-config.yaml is not a file` (expected for this repo; no config exists).
- QA fix (fixer-codex-20260612T070053Z-7032): Addressed the HIGH finding from
  qa-codex-20260612T065532Z-7032. `xsource invoice add` and `xsource invoice reemit`
  now catch invoice validation `ValueError`s and print a concise operator error before
  exiting non-zero, rather than surfacing a traceback. The cockpit invoice details step
  now validates `invoice_date` and optional `due_date` before review/apply, and the
  cockpit apply step catches any final `capture_invoice` validation error and returns
  `StepResult(ok=False)`.
- Verification: focused RED
  `uv run pytest tests/cli/test_runtime_commands.py::test_invoice_add_reports_invalid_date_without_traceback tests/cli/test_runtime_commands.py::test_invoice_reemit_reports_invalid_date_without_traceback tests/walks/test_invoice_capture_walk.py::test_invoice_details_step_rejects_malformed_invoice_date tests/walks/test_invoice_capture_walk.py::test_invoice_details_step_rejects_malformed_due_date tests/walks/test_invoice_capture_walk.py::test_invoice_apply_step_reports_invalid_date_without_raising -q`
  returned five failures: two CLI paths produced empty output with uncaught `ValueError`,
  two cockpit details-step paths returned `ok=True`, and cockpit apply raised `ValueError`.
- Verification: focused GREEN
  `uv run pytest tests/cli/test_runtime_commands.py::test_invoice_add_reports_invalid_date_without_traceback tests/cli/test_runtime_commands.py::test_invoice_reemit_reports_invalid_date_without_traceback tests/walks/test_invoice_capture_walk.py::test_invoice_details_step_rejects_malformed_invoice_date tests/walks/test_invoice_capture_walk.py::test_invoice_details_step_rejects_malformed_due_date tests/walks/test_invoice_capture_walk.py::test_invoice_apply_step_reports_invalid_date_without_raising -q`
  returned `5 passed in 0.06s`.
- Verification: nearby regression suite
  `uv run pytest tests/cli/test_runtime_commands.py tests/walks/test_invoice_capture_walk.py -q`
  returned `14 passed in 2.99s`.
- Verification: full suite `uv run pytest -q` returned `264 passed in 5.63s`.
- Verification: `uv run ruff check .` returned `All checks passed!`.
- Verification: `uv run mypy` returned `Success: no issues found in 60 source files`.
- Verification: `pre-commit run --all-files` returned `InvalidConfigError:
  .pre-commit-config.yaml is not a file` (expected for this repo; no config exists).
- Rebase check: `git fetch origin` then `git rebase origin/main` returned
  `Current branch claude/plan-invoice-to-xbook is up to date.`
- Next concrete step: push final handoff note, mark ready, move label to
  `agent:needs-qa`, post DONE.
