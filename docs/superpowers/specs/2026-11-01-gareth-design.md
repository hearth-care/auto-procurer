# Gareth: a procurement colleague in Google Chat and the cockpit

Date: 1 November 2026. Status: stage 1 implemented on the `claude/gareth-design` branch (1 November 2026); later stages still draft.

## Why

The operator runs a care home and buys trade services and contracts: electrical testing, gas
servicing, waste, energy, fire safety and so on. Today the work goes like this. Search Google for
local firms, ring them, get prices, chase quotes, play the best price off against the others
("I've got £780, can you beat it?"), book the winner, tell them to meet the maintenance lead
(on site 08:00–16:00) and to send the quote to the accounts address, then file the paperwork
somewhere. A year later, nobody remembers who did the job, what it cost or why that firm was
picked.

xsource already does part of this: it finds firms near the home, publishes a shortlist Sheet,
drafts outreach emails (never sends), watches for replies and captures invoices. What it lacks
is a colleague you can talk to, a record that lasts beyond one search, the phone side of the
work, and a tidy trail of documents.

Gareth is that colleague. He is xsource with a name, a Google Chat front door, a lasting
workbook, the phone calls folded in, and a filing habit.

## What success looks like

- The operator can ask "who do we use for fire risk assessments, and when's the next one due?"
  or "where did we get to last time with the electricity contract?" and get a straight answer
  with a link to the evidence.
- From any job, every price, call and email can be followed back by link to the original
  document, and the black book says why the winning firm was chosen.
- After a morning of phone calls, the operator checks Gareth's summary instead of typing notes.
- Contract renewals show up early enough to shop around (the notice deadline turns red when it
  is less than 60 days away).
- New suppliers reach Xero via Milo without the operator re-keying them.

## Non-goals

- Gareth never sends an email, places a phone call, books a job or pays anything. He drafts, files,
  records and reminds. The operator presses Send in Gmail and makes the calls.
- No new phone system. Calls stay on 3CX; recordings stay in 3CX.
- No rewrite of xsource's research, watcher or invoice code beyond what this design needs.
- No shared group chat room. Gareth is a one-to-one DM, like the other workers' personas.

## Anti-goals (would count as failure even if it technically works)

- An email reaching a firm that the operator did not personally send.
- Gareth reading, copying or summarising resident or family calls. The transcripts folder
  holds those alongside supplier calls; Gareth must only open transcripts whose number matches
  a firm he is dealing with.
- Writing a price, stage or booking into the Sheet from a transcript without the operator
  confirming it first.
- A second, competing record. The workbook, the Drive folders and xsource's own store must agree;
  if they disagree, the store is right and the Sheet is redrawn from it.
- Gareth sounding like a chatbot to tradespeople. Drafts follow the existing tone: casual,
  friendly British, precise only on the job details.

## Constraints

- Public repository: no real supplier names, personal email addresses, internal hostnames or
  machine paths in code, docs or fixtures. Use made-up firms.
- Draft-never-send stays enforced by `tests/test_no_send_endpoints.py`.
- Every mutating action in the cockpit or in Chat goes through the framework's single write gate
  (`confirm_apply`). Agent mode (`--agent-stdio`) stays dry-run without `--allow-apply`.
- Chat and the cockpit share one code path. Chat drives the same cockpit walks through
  `clonway_cockpit.conversation.Conversation`; it has no write path of its own. Every new
  cockpit page ships with its `model_*` twin.
- Runs on the existing Cloud Run jobs and state bucket.
- New Google access (reading the transcripts folder, writing to the Suppliers Drive folders,
  the Chat app itself) is an auth change and needs the operator's explicit approval before it
  is requested.

## The contract

This design is binding on the implementation through four files that change only together with
the code:

| File | Fixes |
|---|---|
| `docs/contracts/gareth-workbook-v1.md` | workbook tab names, column headers and order, formulas, stages |
| `docs/contracts/gareth-calls-v1.md` | transcript title pattern, header fields, number normalisation, de-duplication |
| `docs/contracts/gareth-screens-v1.md` | cockpit page ids, Chat cards and their actions, nudge kinds |
| `docs/superpowers/specs/2026-11-01-gareth/system.html` and `sheet-layout.html` | the reviewed mock-ups: layout and what appears where |

The first task of the plan writes `tests/test_gareth_contracts.py`, which parses the contract
tables and fails until the code's tab names, columns, formulas, page ids, card actions, nudge
kinds and transcript parsing match them. After that, any change to a screen, column or rule
means editing the contract in the same commit, and renaming or removing an existing item bumps
`contract_version`. Where the mock-ups and a contract disagree, the contract wins and the
mock-up is corrected in the same change.

## The parts

### 1. Name and voice

The persona is Gareth (`config/personas/gareth.toml` and `config/souls/gareth.md`, following
the framework's persona layout). Outreach drafts are signed with `XSOURCE_OPERATOR_DISPLAY_NAME` (default Gareth); the From name and address come from
`XSOURCE_MAILBOX_DISPLAY_NAME` and `XSOURCE_MAILBOX_ADDRESS`. Gareth gets his own mailbox, a `gareth@` alias
on the company domain that the operator sets up; drafts are created there and replies come back
there. [ASSUMPTION: the alias name; the operator to confirm.]

### 2. The flow of a job

The operator decided this order: phone first, then email, then email from then on.

1. **Ask.** "Need an EICR for the whole building" in Chat or via shelf A in the cockpit.
2. **Find.** Gareth searches as today (Maps, distance from the home, Companies House check),
   shows the shortlist, and waits for an OK before creating the job tab.
3. **Call list.** Gareth lists who to ring today, with numbers that keep their leading 0.
4. **Calls.** The operator rings them on 3CX. Gareth reads the transcripts (part 5) and proposes
   each firm's outcome, price, dates and email address. The operator confirms or corrects.
5. **Follow-up email.** For each keen firm, Gareth drafts a follow-up email in his mailbox
   referring to the call. From here on the firm is contacted by email.
6. **Replies.** The existing watcher reads replies and pulls out prices.
7. **Haggle.** Once enough prices are in, Gareth suggests going back to a firm with the best
   price so far, and drafts "can you beat £X?" on the operator's say-so.
8. **Book.** The operator picks the winner and a date. Gareth drafts the booking email: the date,
   meet the maintenance lead on site 08:00–16:00, and send the quote and invoice to the accounts
   address. [ASSUMPTION: the accounts address is `accounts@` on the company domain; the operator
   to confirm.]
9. **Close.** Gareth creates or updates the firm's Drive folder, files the quote and the firm's
   call transcripts there, writes the black book row and hands the new supplier to Milo
   (part 7).

### 3. When Gareth speaks up

Gareth messages the operator in Chat only when something needs them or something they care
about has happened, and stays quiet otherwise:

- drafts are ready to send;
- a new price has come in (with the current league table for that job);
- it is time to haggle;
- calls need making, or a call needs checking;
- a number he cannot place (outbound to a business number not on any job);
- a booking has been made;
- a quote or invoice has reached accounts;
- a morning note at 08:30 on weekdays summarising open jobs and anything due.

### 4. The workbook (Google Sheet)

One workbook that lasts, kept in Drive under `9-Operations › Suppliers › _Shortlists`. It
replaces creating a new Sheet per search. The firm's name is the column that joins every tab.
Columns marked "formula" are worked out by the Sheet and never typed.

- **Board**: one row per open job. Job, link to the job tab, stage, firms keen (formula), quotes
  in (formula), best price (formula, the lowest price on the job tab), best firm (formula, the
  firm on that row), next step, waiting on.
- **A tab per job**, named like "EICR Nov 2026": one row per firm, with firm, contact, phone
  (stored as text so the leading 0 survives), email, website, address, miles, stage, first
  price, latest price, last contact, a link to that firm's calls, a link to the email thread,
  notes. The columns can suit the trade: energy compares unit rate, standing charge, term and
  estimated yearly cost instead of one price.
- **Black book**: one row per kind of job. Kind of job, firm, contact, phone, email, last used,
  last price, contract ends, notice to give, tell them by (formula: contract end minus notice,
  red when under 60 days away), link to the firm's Drive folder, "how we chose them" (link to
  the job tab), in Xero (tick).
- **Old job tabs** stay, so "where did we get to last time" is a link away.
- **Log**: dated lines of what happened, newest first.

The Sheet is a view. xsource's store (the state bucket) is the record; Gareth redraws Sheet rows
from it. Hand edits by the operator to price, stage or notes on a job tab are read back into the
store by the existing sheet sync, as today.

### 5. Phone calls

Every company call is recorded by 3CX, transcribed, and saved as a Google Doc in the operator's
`Phone log › Transcripts` folder. The recordings themselves stay in 3CX and are not needed.
The exact title pattern, header fields, number rules and examples are fixed in
`docs/contracts/gareth-calls-v1.md`.

Each transcript's title is `YYYY-MM-DD HHMM <direction or menu option> <number> [<call id>]`,
for example `2026-10-31 1145 Outbound 01632960100 [01dd-…]`. The body begins with a header:
direction, the number called or calling, who answered, talk time, a caller type (for example
"Supplier — Sam from Example Co"), a summary, and "Follow-up promised" where there is one. Then the
full transcript.

Gareth's handling:

1. **Match by title only.** Take the number from the title and normalise it: strip spaces, and
   prefix the home's local area code (01632) to six-digit local numbers such as `960202`. Look
   it up against the phone numbers on open job tabs first, then the black book. Do not open a
   transcript whose number does not match.
2. **Deduplicate by call id.** The same call can be saved more than once (one call on
   31 October 2026 was saved 33 times, five minutes apart). Treat the bracketed call id as the
   key.
3. **Unmatched outbound business numbers** (landlines and 03/08 numbers, not mobiles) made
   during an open job's calling stage are offered to the operator in Chat: "who was 01632…?".
   Answering files the call and saves the number to that firm. Inbound unmatched calls are
   ignored.
4. **Read.** For a matched call, use the summary, follow-up and transcript to propose: outcome
   (keen, declined, no answer, call back), price if quoted, dates, contact name, email address.
   Show it to the operator as one card per round of calls.
5. **Record on confirmation.** Update the firm's row on the job tab (stage, price, last contact,
   calls link) and add a Log line.
6. **File.** Put a copy of the transcript in the job's folder under the firm
   (`_Shortlists › <job> › <firm>`), named `YYYY-MM-DD Call - <firm>`. The original stays in
   the transcripts folder untouched. When the firm wins, its copies move into its supplier
   folder.

### 6. Drive folders

The operator tidied supplier documents into one place on 1 November 2026:
`9-Operations › Suppliers`, one folder per firm named `<Firm> - <what they do>`, plus
`_Shortlists`, `_Former suppliers` and `_Not suppliers - to file`.

Gareth follows that convention:

- When a firm wins a job, find its folder by name, or create `<Firm> - <what they do>`.
- File quotes, booking confirmations, certificates and contracts there, named
  `YYYY-MM-DD <Type> - <description>` (for example `2026-11-04 Quote - EICR`).
- Each job gets a folder in `_Shortlists` holding call copies for every firm on it, so firms
  that lost still have their trail.
- A firm the home stops using has its folder moved to `_Former suppliers` when the operator
  says so. Gareth never deletes anything in Drive.

### 7. Hand-off to Milo for Xero

When a new firm wins a job and is not already in Xero, Gareth hands it to Milo (the bookkeeper
worker) with name, address, email, phone and what they supply, and Milo creates the Xero
contact through its own approval flow. Gareth ticks "In Xero" when Milo confirms. Gareth does
not touch Xero himself. The hand-off uses the fleet's existing cross-worker channel; if none
fits, the builder proposes one.

### 8. The two front doors

**Google Chat.** A DM with Gareth. Free text in, plain text and cards out. Questions are
answered from the store and the workbook. Anything that writes (creating a job tab, recording a
call outcome, creating a draft, filing to Drive) appears as a card with a button; pressing it is
the `confirm_apply` step. Only the operator's account may talk to Gareth (the framework's
operator allowlist).

**Cockpit (terminal).** Existing shelves stay. New pages: Board (open jobs at a glance), Call
list (who to ring today, per job), Calls to file (matched calls awaiting confirmation and
unmatched numbers). Each has its `model_*` twin, so Chat and agent mode can drive them.

The mock-ups the operator reviewed (system diagram, interaction points, Chat and terminal
screens, call pipeline, document trail) are the reference for layout; exact wording and
ordering are the builder's call.

## Decided by the operator

- The name Gareth, separate from Milo.
- Google Chat as the main interface, with the terminal cockpit as an equal second door.
- Phone first, email after, email from then on.
- One lasting workbook with Board, job tabs, Black book, old job tabs and Log; the firm as the
  join key; full contact details on job tabs and in the black book; a Drive folder link and
  contract renewal dates in the black book.
- Supplier documents live in `9-Operations › Suppliers`, one folder per firm.
- Calls are matched to firms by phone number using the 3CX transcripts in Drive; recordings are
  not needed.

## My calls (the operator may overrule)

- Losing firms get no supplier folder; their calls live in the job's `_Shortlists` folder.
- Gareth only opens transcripts whose number matches a firm, and ignores inbound unmatched calls.
- The 60-day red warning, the 08:30 weekday morning note, and the file-naming pattern.
- The store is the record and the Sheet is redrawn from it.

## Settled after the builder check (my calls)

A reviewer read this as the builder would. These answers are mine; the operator may overrule.

1. **Store.** The store gains what the Sheet shows: job stage, each firm's stage, first and
   latest price, the call ids already filed, Drive folder id, contract end, notice days and the
   In Xero tick. Stages are stored, not derived. Records carry a schema version and the loader
   upgrades old records in place on read, so the live bucket needs no separate migration step.
2. **Sheet edits.** Before every redraw Gareth reads back the hand-editable columns listed in the
   workbook contract and saves them to the store, then redraws. Formula columns and `Firm` are
   protected. A firm is renamed only through Gareth.
3. **Workbook identity.** As in the workbook contract: one id in config, ` (2)` on clashing tab
   names, old per-request Sheets left readable. The Publish shelf stays for the staff directory.
4. **Energy tabs.** The Board formula finds the price column by header, so energy tabs work.
   `Emailed` counts as keen.
5. **Chat.** Follow the framework's existing Chat add-on server and the other workers' pattern;
   the operator allowlist is the framework's. The morning note is a Cloud Scheduler job like the
   watcher and signal scans.
6. **Milo hand-off.** Reuse the invoice hand-off pattern: a `supplier.new` signal with its own
   contract file, and Milo writes an acknowledgement that sets the tick. This needs a matching
   change in the bookkeeper repo, planned as its own PR.
7. **Mailbox.** Build against the current mailbox with the address and display name in config;
   switching to the `gareth@` alias is a config change once the operator has set it up. The
   watcher reads whichever mailbox is configured.
8. **Mock-ups.** They fix layout and what appears where. Visual details (colours, red warning
   styling) are checked by eye, not by tests.
9. **Call matching.** An open job beats the black book; between open jobs, the most recent wins.
   Filed call ids are kept in the store so a call is never filed twice. Calls are gathered into
   one Chat card once 30 minutes pass with no new matched call.

## Left to the builder

- How to split the work into stages and in what order to ship them. A sensible first slice is
  the workbook and the Board, then calls, then Chat.
- Where the Chat app is hosted (its own Cloud Run service or alongside the jobs), how often the
  transcripts folder is polled, and how state for half-finished conversations is kept.
- Migration of existing requests and black-book entries into the new workbook.
- The fix for the existing issues found in the live run: drafts marked "Asked" before they are
  sent, phone numbers losing their leading 0, the shortlist not being shown before apply, and
  "care home nearby" appearing with no town.

## Still open

- The `gareth@` mailbox alias and the accounts address need the operator's confirmation.
- The Google access Gareth needs (read the transcripts folder, write to the Suppliers folders,
  a Chat app) needs the operator's approval before it is requested.
