# Gareth call transcripts v1 contract

contract_version: 1

How Gareth reads the phone system's call transcripts. The design is in
`docs/superpowers/specs/2026-11-01-gareth-design.md` (part 5).

This file is normative. `tests/test_gareth_contracts.py` checks the title pattern, the header
fields, number normalisation and de-duplication against the examples below. The examples use
made-up numbers.

## Where they come from

The phone system records every company call, transcribes it and saves one Google Doc per call
into a transcripts folder in Drive, configured as `XSOURCE_TRANSCRIPTS_FOLDER_ID`. Recordings
are not used. The folder also holds resident and family calls, so Gareth must not open a
transcript until its number has matched a firm.

## Title

```
YYYY-MM-DD HHMM <label> <number> [<call id>]
```

`<label>` is `Outbound`, `Direct line`, or an inbound menu option such as `1 Existing residents`.

| Example title | date | time | direction | number | call id |
|---|---|---|---|---|---|
| `2026-10-31 1145 Outbound 01865000001 [01dd-0000-0000-000000000001]` | 2026-10-31 | 11:45 | outbound | 01865000001 | 01dd-0000-0000-000000000001 |
| `2026-10-14 0825 Outbound 850001 [01dd-0000-0000-000000000002]` | 2026-10-14 | 08:25 | outbound | 01822850001 | 01dd-0000-0000-000000000002 |
| `2026-11-01 0932 4 Anything else 07700900001 [01dd-0000-0000-000000000003]` | 2026-11-01 | 09:32 | inbound | 07700900001 | 01dd-0000-0000-000000000003 |
| `2026-11-01 0700 Direct line 01865000002 [01dd-0000-0000-000000000004]` | 2026-11-01 | 07:00 | inbound | 01865000002 | 01dd-0000-0000-000000000004 |

Titles that do not match are skipped and counted in Diagnostics.

## Number normalisation

| Raw | Normalised | Rule |
|---|---|---|
| `01822 850001` | `01822850001` | strip spaces |
| `850001` | `01822850001` | six digits: prefix the home's area code (`XSOURCE_LOCAL_AREA_CODE`, default `01822`) |
| `+441822850001` | `01822850001` | `+44` becomes `0` |
| `111` | — | three digits or fewer: never matched |

## Header fields

The body begins with these lines before the word `Transcript`:

| Field | Example | Used for |
|---|---|---|
| `Call <id>` | `Call 01dd-…` | de-duplication |
| direction line | `Sat 31 Oct 2026 11:45, outbound, called 01865000001, …, answered by <name>, talk 259s` | who made the call, length |
| `Caller type:` | `Supplier — <name> from <firm>` | contact name |
| `Summary:` | one paragraph | outcome, price, dates |
| `Follow-up promised:` | optional | next step |

## Matching and de-duplication

1. Match the normalised number against open job tabs, then the black book. No match: do not
   open the document.
2. Unmatched outbound calls to landline, `03` or `08` numbers while a job is in `Calling` are
   offered to the operator; unmatched inbound calls and mobiles are ignored.
3. The call id is the key. A second document with the same call id is the same call and is
   skipped.
