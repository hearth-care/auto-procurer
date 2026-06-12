# payment.required v1 contract

contract_version: 1

This contract defines the xsource to xbook invoice handoff. xsource owns invoice
capture and emits a thin fleet Signal. xbook owns AP intake and writes an ack
record back to the shared handshake file.

## Signal

Transport: the existing worker signal snapshot for xsource.

Kind: `payment.required`

Required wire fields:

| Field | Value |
|---|---|
| `worker` | `xsource` |
| `kind` | `payment.required` |
| `title` | `Invoice <invoice_number or id> - <supplier name>` |
| `detail` | `<currency> <amount> - <description>` |
| `level` | `warn`, or `error` when overdue |
| `urgency` | `normal`, or `high` when overdue |
| `due_at` | invoice `due_date`, if set |
| `capability_key` | `invoice.capture` |
| `focus` | invoice id |
| `dedup_key` | `xsource|invoice|<invoice id>` |
| `source_ref` | invoice id |
| `source_id` | invoice id |

The full invoice remains in `state/xsource/invoices.jsonl`; consumers fetch it by
`source_id`. The signal payload intentionally stays within the current shared
fleet Signal shape.

## Idempotency

`dedup_key` is stable for the life of the invoice. xsource emits the same
obligation on every scan while the invoice is in `captured`, `emitted`, or
`re-emitted`. xbook must treat repeated records with the same key as the same AP
obligation.

## Ack Handshake

Ack records are JSONL entries in `payment-required-acks.jsonl` at the shared
state handoff location. Locally, `xsource invoice sync-acks` defaults to
`XSOURCE_STATE_DIR/payment-required-acks.jsonl`.

Ack fields:

| Field | Type |
|---|---|
| `invoice_id` | string |
| `consumer_run_id` | string |
| `disposition` | `accepted` or `rejected:<reason>` |
| `timestamp` | ISO datetime |
| `contract_version` | integer, currently `1` |

`accepted` transitions `emitted` invoices to `acknowledged`. `rejected:<reason>`
transitions them to `rejected` and leaves an operator-visible `action.required`
signal until corrected. A non-integer or unsupported `contract_version` is
skipped (not a hard error), so one malformed record never stops the sync.

Rejected invoices have a real recovery path: the operator corrects and re-emits
with `xsource invoice reemit <id>` (transitions `rejected → emitted`, clearing
the rejection reason), or abandons it with `xsource invoice write-off <id>`
(`rejected → written_off`). A re-emitted invoice is acked exactly like a freshly
emitted one.

## Fixtures

- `tests/contracts/fixtures/latest.jsonl` is the golden xsource signal snapshot.
- `tests/contracts/fixtures/acks.jsonl` is the golden xbook ack record.
