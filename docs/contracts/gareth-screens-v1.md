# Gareth screens v1 contract

contract_version: 1

The pages, cards and nudges the operator sees in the cockpit and in Google Chat. The design is
in `docs/superpowers/specs/2026-11-01-gareth-design.md` (parts 3 and 8); the reviewed mock-up is
`docs/superpowers/specs/2026-11-01-gareth/system.html`.

This file is normative. `tests/test_gareth_contracts.py` checks that every page below exists in
the cockpit registry with a `model_*` twin, that every write action routes through
`confirm_apply`, and that every nudge kind has a builder. Wording on screen is the builder's
call; ids, actions and the write/read split are not.

## Cockpit pages (new)

| Page id | Title | Shows | Write actions (all via `confirm_apply`) |
|---|---|---|---|
| `board` | Board | open jobs: stage, quotes in, best price, waiting on | none |
| `call_list` | Call list | per job, firms to ring today with number and last outcome | `mark_no_answer` |
| `calls_to_file` | Calls to file | matched calls with Gareth's proposed outcome; unmatched numbers | `confirm_call`, `correct_call`, `assign_number` |

Existing shelves A–E and G stay. Shelf C (Black book) gains the contract and folder columns
from the workbook contract.

## Chat cards

Every card that writes carries a primary button that performs the action through the same
cockpit walk as the matching cockpit page.

| Card | Buttons | Walk |
|---|---|---|
| Shortlist | `Start job`, `Not yet` | request_new apply |
| Calls filed | `Looks right`, `Fix a price`, `Read transcript` | calls_to_file `confirm_call` / `correct_call` |
| Who was this number | free-text reply | calls_to_file `assign_number` |
| Draft ready | `Open in Gmail` | read-only link |
| Haggle | `Draft it`, `Not yet` | outreach draft |
| Choose winner | `Book <firm>`, `Not yet` | booking draft, Drive filing, Milo hand-off |

## Nudges

| Kind | When | Quiet otherwise |
|---|---|---|
| `morning_note` | 08:30 weekdays, if any job is open or any renewal is within 60 days | yes |
| `drafts_ready` | new drafts in Gareth's mailbox | yes |
| `price_in` | a new price recorded, with that job's league table | yes |
| `time_to_haggle` | at least 3 prices on a job and none asked to beat the best | yes |
| `calls_to_check` | matched transcripts waiting | yes |
| `unknown_number` | unmatched outbound business number during `Calling` | yes |
| `booked` | a booking draft created | yes |
| `quote_to_accounts` | a quote or invoice reached accounts | yes |
