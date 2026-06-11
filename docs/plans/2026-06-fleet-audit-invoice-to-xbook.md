# [Plan] Invoice capture → xbook AP handoff

**Status:** implementation in progress on PR #13
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

- [ ] `src/xsource/signals/build.py`: `build_payment_required_signals` composed
      into the horizon scan; overdue escalation.
- [ ] Handshake ack reader wired into the nightly sync path
      (`src/xsource/cli/request.py` sync-all or a sibling `invoice sync`).
- [ ] Tests: emission only in emittable states; stable dedup keys; ack
      transitions; rejected-invoice operator signal.

### Phase 4 — contract artifact (Wave 3, S)

- [ ] `docs/contracts/payment-required-v1.md`: the contract above, frozen.
- [ ] Shared fixtures: a golden `latest.jsonl` slice + ack records; a contract
      test that validates the emitter's output against the fixtures.
- [ ] Hand the fixture set to the books-worker repo (cross-repo PR, tracked
      there).

## Acceptance criteria

- [ ] An invoice can be captured (CLI and walk), linked to its request and
      supplier, and survives a store round-trip.
- [ ] Capturing an invoice against a chosen supplier appends an `"invoiced"`
      price-history row; a >tolerance quote-vs-invoice gap raises a variance
      flag and a signal.
- [ ] Every unsettled, emittable invoice produces exactly one
      `payment.required` signal per scan with a stable `dedup_key`; settled and
      acknowledged invoices produce none.
- [ ] A consumer ack flips the invoice state; a rejection becomes an
      operator-visible `action.required` item.
- [ ] The contract doc + fixtures exist and the emitter is tested against them.
- [ ] No new write path bypasses the cockpit gate; the worker still never sends
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

- Current phase: Phase 3 — signal emission + ack ingestion.
- Completed: Phase 1 schema/store slice with `InvoiceRecord`, lifecycle validation,
  `invoices.jsonl` `SyncedStore`, and focused tests.
- Completed: Phase 2 capture/import/CLI/cockpit slice with price-history linkage,
  supplier mismatch warnings, variance detection, idempotent CSV import, root
  `xsource invoice` commands, `invoice.capture`, and the invoices attention pill.
- Verification: `uv run pytest tests/store/test_models.py tests/store/test_remote.py -q`
  returned `19 passed in 0.03s`.
- Verification: `uv run pytest tests/invoices/test_capture.py tests/cli/test_runtime_commands.py tests/test_cockpit_render.py -q`
  returned `11 passed in 4.88s`.
- Decisions: `build_stores` now returns `(suppliers, requests, invoices)`; existing callers
  ignore the invoice store until their phase uses it.
- Decisions: invoice capture stores money as `amount_minor`; variance checks normalise older
  supplier quote rows with `amount` by treating them as pounds.
- Known-failing tests: none at this handoff point.
- Next concrete step: write failing Phase 3 tests for `payment.required` emission,
  ack ingestion, rejected-invoice operator signals, and horizon composition.
