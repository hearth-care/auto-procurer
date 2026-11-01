# Gareth workbook v1 contract

contract_version: 1

The lasting procurement workbook Gareth keeps in Google Sheets. The design is in
`docs/superpowers/specs/2026-11-01-gareth-design.md`; the reviewed mock-up is
`docs/superpowers/specs/2026-11-01-gareth/sheet-layout.html`.

This file is normative. `tests/test_gareth_contracts.py` parses the tables below and fails if
the implementation's tab names, column headers, column order or formulas differ. Changing the
workbook means changing this file in the same commit, and bumping `contract_version` if an
existing column is renamed, removed or reordered.

## Tabs

| Order | Tab name | Kind |
|---|---|---|
| 1 | `Board` | fixed |
| 2 | `Black book` | fixed |
| 3 | `Log` | fixed |
| 4+ | `<Job> <Mon YYYY>`, e.g. `EICR Nov 2026` | one per job, newest first, never deleted |

## Board

One row per open job. "formula" columns are written as Sheet formulas, never as values.

| Col | Header | Source |
|---|---|---|
| A | Job | store: request title |
| B | Job tab | link to the job tab |
| C | Stage | store: request stage (see Stages) |
| D | Firms keen | formula: count of job-tab rows with stage `Keen`, `Emailed`, `Quoted` or `Booked` |
| E | Quotes in | formula: count of non-empty price-column cells on the job tab |
| F | Best price | formula: `=MIN('<tab>'!<P>:<P>)` |
| G | Best firm | formula: `=INDEX('<tab>'!B:B, MATCH(MIN('<tab>'!<P>:<P>), '<tab>'!<P>:<P>, 0))` |

`<P>` is the job tab's price column, found by header: `Latest price` (column K) on a standard
tab, `Est. yearly cost` (column M) on an energy tab.
| H | Next step | store |
| I | Waiting on | store: `You: <action>` or `Nobody` |

## Job tab (standard trades)

| Col | Header | Notes |
|---|---|---|
| A | # | rank |
| B | Firm | join key across tabs |
| C | Contact | |
| D | Phone | written as text so the leading 0 survives |
| E | Email | |
| F | Website | |
| G | Address | |
| H | Miles | from the home postcode |
| I | Stage | see Stages |
| J | First price | £, number |
| K | Latest price | £, number; Board best price reads this column |
| L | Last contact | `D Mon · call` or `D Mon · email` |
| M | Calls | link to the firm's folder of call transcripts for this job |
| N | Email thread | link to the Gmail thread |
| O | Notes | free text, hand edits read back by sheet sync |

## Job tab (energy)

Same as the standard tab with J–K replaced by J `Term`, K `Unit rate`, L `Standing charge`,
M `Est. yearly cost`; the later columns shift right by two. Board best price reads
`Est. yearly cost`.

## Who may edit what

| Columns | Rule |
|---|---|
| All formula columns, Board A–C and H–I, Log, job-tab `Firm` | protected; written only by Gareth |
| Job tab: Contact, Phone, Email, Stage, prices, Notes | hand-editable; read back into the store before every redraw |
| Black book: Contact, Phone, Email, Contract ends, Notice to give | hand-editable; read back the same way |

## Workbook identity

One workbook, id in `XSOURCE_WORKBOOK_ID`. A second job with the same tab name in the same month
gets ` (2)`. Sheets made per request before this contract stay where they are, read-only.

## Black book

One row per kind of job.

| Col | Header | Notes |
|---|---|---|
| A | Kind of job | |
| B | Firm | join key |
| C | Contact | |
| D | Phone | text |
| E | Email | |
| F | Last used | date |
| G | Last price | |
| H | Contract ends | date or blank |
| I | Notice to give | days or blank |
| J | Tell them by | formula: `=IF(H="","",H-I)`; red when under 60 days away |
| K | Documents | link to the firm's Drive folder |
| L | How we chose them | link to the job tab |
| M | In Xero | tick, set when Milo confirms |

## Log

| Col | Header |
|---|---|
| A | When |
| B | Job |
| C | What happened |

Newest first.

## Stages

Job-tab firm stages, in order: `To call`, `No answer`, `Keen`, `Emailed`, `Quoted`, `Declined`,
`Booked`, `Not chosen`.

Board job stages, in order: `Searching`, `Calling`, `Waiting for prices`, `Haggling`, `Booked`,
`Done`.
