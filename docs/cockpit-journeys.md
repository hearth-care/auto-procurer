# xsource cockpit journey map

**Last verified:** 2026-07-02 against PR #29 (`claude/plan-operator-surfaces`).

For each journey this document states:
- **Entry point** — shelf key and capability key(s)
- **Current state** — implemented / config-gated / placeholder, with the code path
- **Preconditions** — env vars, tokens, or data required before the journey runs
- **Mutation risk and gate** — what gets written and how the write is guarded
- **Target live path** — what the full wired version would do

---

## Navigation notes

**Shelves run A, B, C, D, E, G. There is no shelf F.**

**Global shelf keys (A–E, G) are inactive while a shelf menu is open.** Inside a shelf
menu the keys cycle through menu items (digits, up/down) or go back (Q/Esc). The global
shelf hotkeys only fire on the home screen. This is a framework-level design: exit the
current shelf first, then navigate to another.

---

## Journey 1 — New request (shelf A)

**Entry point:** shelf `A` → `request.new`, `request.trigger`, `request.reorder`

### 1a · `request.new` — implemented (config-gated)

**Current state:** fully implemented walk handler.
Code path: `_request_new_handler` → `_need_step` → `_triage_step` → `_research_step` → `_review_apply_step`.

**Preconditions:**

| Precondition | Source |
|---|---|
| `GOOGLE_MAPS_API_KEY` | env var — places search |
| `ANTHROPIC_API_KEY` | env var or Secret Manager — LLM triage + ranking |
| `XSOURCE_SHEETS_TOKEN_PATH` | path to OAuth token file — Sheet creation |
| GCS store reachable | `XSOURCE_BUCKET` + ADC — supplier/request persistence |
| Research budget not blocked | `xsource/budget.py` — tracks spend against monthly cap |
| `XSOURCE_HOME_POSTCODE` | env var — radius search origin |

If any precondition is absent the walk shows a preflight screen and declines to continue.

**Mutation risk and gate:**
- Creates one Google Sheet and writes one request record + shortlist to the GCS store.
- Does not send or draft any email.
- Gate: `confirm_apply` (cockpit write gate, also dry-run in agent mode unless `--allow-apply` is passed).
- Reversible: Sheet can be deleted; store records can be removed by id.

**Target live path:** current implementation is the target state.

---

### 1b · `request.trigger` — implemented (config-gated)

**Current state:** fully implemented walk handler.
Code path: `_request_trigger_handler` → `_trigger_step` (parses JSON payload or file) → `_triage_step` → `_research_step` → `_review_apply_step`.

**Preconditions:** same as `request.new` plus a trigger JSON payload (inline or file path).

**Mutation risk and gate:** identical to `request.new`.

**Target live path:** current implementation is the target state.

---

### 1c · `request.reorder` — implemented (config-gated)

**Current state:** fully implemented walk handler.
Code path: `_request_reorder_handler` → `_reorder_proposal_step` → `_reorder_research_step` → `_review_apply_step`.

For **reorder**: builds a single-candidate result from the incumbent and skips LLM research.
For **re-tender**: runs full triage + research, then injects the incumbent into the shortlist.

**Preconditions:** GCS store reachable, supplier id known, plus same keys as `request.new`
for the re-tender branch.

**Mutation risk and gate:** identical to `request.new`.

**Target live path:** current implementation is the target state.

---

## Journey 2 — Requests (shelf B)

**Entry point:** shelf `B` → `request.list`, `request.sync`

### 2a · `request.list` — implemented (read-only)

**Current state:** fully implemented read-only walk.
Code path: `_request_list_handler` → `_request_list_step`.
CLI twin: `xsource request list`.

**Preconditions:** store loaded. Offline read-only cache still passes; construction failure blocks.

**Mutation risk:** read-only — no mutations.

**Walk steps:** List. The result reports open and total request counts, and surfaces any
current-load JSONL quarantine count.

**Target live path:** current implementation is the target state.

---

### 2b · `request.sync` — placeholder card / live CLI

**Current state:** `run=None` — cockpit card is a static reference only.
The CLI path (`xsource request sync` / `xsource request sync-all`) is fully implemented.
Code path: `src/xsource/cli/request.py` → `src/xsource/sheet/sync.py`.

**Preconditions:**

| Precondition | Source |
|---|---|
| `XSOURCE_SHEETS_TOKEN_PATH` | OAuth token — Sheet read |
| GCS store reachable | supplier/request persistence |

**Mutation risk:** writes parsed Sheet data back into the request and black-book records.
`sync-all` processes every open request; there is currently no read-only `--dry-run`
preview mode.

**Target live path:** cockpit walk wired to the existing sync code; `sync-all` gains a
`--dry-run` preview so operators can inspect before mutating.

---

## Journey 3 — Black book (shelf C)

**Entry point:** shelf `C` → `book.search`, `book.import`

### 3a · `book.search` — implemented (read-only)

**Current state:** fully implemented read-only walk.
Code path: `_book_search_handler` → `_book_search_term_step` → `_book_search_results_step`
→ `src/xsource/book/search.py`.
CLI twin: `xsource book search TERM`.

**Preconditions:** store loaded. Offline read-only cache still passes; construction failure blocks.

**Mutation risk:** read-only — no mutations.

**Walk steps:** Term → Results. Results match supplier name, category, or tag and include
the current-load supplier-store quarantine count when present.

**Target live path:** current implementation is the target state.

---

### 3b · `book.import` — implemented (confirm-apply gated)

**Current state:** fully implemented walk.
Code path: `_book_import_handler` → `_book_import_file_step` → `_book_import_preview_step`
→ `_book_import_apply_step` → `src/xsource/book/importer.py`.
CLI twin: `xsource book import CSV [--dry-run]`.

**Preconditions:** supplier store reachable for writes; CSV file path provided.

**Mutation risk:** writes new supplier records to the GCS store.
Gate: `confirm_apply` required before writing.

**Walk steps:** File → Preview → Apply. Preview uses the same importer with `dry_run=True`;
Apply writes only after the cockpit gate. Re-runs skip existing supplier names.

**Target live path:** current implementation is the target state.

---

## Journey 4 — Publish (shelf D)

**Entry point:** shelf `D` → `book.publish`, `partner.checkatrade`

### 4a · `book.publish` — implemented (confirm-apply gated)

**Current state:** fully implemented walk.
Code path: `_book_publish_handler` → `_book_publish_preview_step` → `_book_publish_apply_step`
→ `src/xsource/book/publish.py` and `src/xsource/sheet/client.py`.
CLI twin: `xsource book publish`.

**Preconditions:** Sheets token file exists, supplier store reachable, and at least one
supplier exists.

**Mutation risk:** regenerates the read-only staff supplier directory (write to Drive/Sheets).
Gate: `confirm_apply` required.

**Walk steps:** Preview → Publish. Publish updates the existing persisted directory sheet
when present, recreates it if the saved sheet is gone, and shares it read-only with the
staff group when configured.

**Target live path:** current implementation is the target state.

---

### 4b · `partner.checkatrade` — placeholder (build-only)

**Current state:** `run=None` — renders a static card only.
Build logic exists at `src/xsource/p4/checkatrade.py` but no post path is wired.
Posting a partner lead requires an explicit operator gate (`--allow-apply`).

**Preconditions:** gate token required to post.

**Mutation risk:** would POST a signed lead to the Checkatrade partner API.
Gate: guarded-apply token handshake — never fires without explicit operator sign-off.

**Target live path:** card wired to the checkatrade module under the guarded-apply gate;
build-only in agent dry-run mode.

---

## Journey 5 — Outreach (shelf E)

**Entry point:** shelf `E` → `request.outreach`, `request.followup`, `watcher.status`

### 5a · `request.outreach` — implemented (config-gated)

**Current state:** fully implemented walk handler. Draft-only — never sends email.
Code path: `_request_outreach_handler` → `_outreach_select_step` → `_outreach_apply_step`
→ `src/xsource/outreach/drafts.py`.

**Preconditions:**

| Precondition | Source |
|---|---|
| `ANTHROPIC_API_KEY` | LLM-generated draft bodies |
| `XSOURCE_GMAIL_TOKEN_PATH` | OAuth token — draft creation |
| GCS store reachable | reads request + supplier records |
| At least one open request | gated by precondition check |

**Mutation risk and gate:**
- Creates Gmail drafts (never sends).
- Gate: `confirm_apply`.
- Reversible: drafts can be deleted from Gmail; outreach metadata can be removed from the request record.

**Target live path:** current implementation is the target state.

---

### 5b · `request.followup` — implemented (config-gated)

**Current state:** fully implemented walk handler. Draft-only — never sends email.
Code path: `_request_followup_handler` → `_followup_select_step` → `_followup_apply_step`
→ `src/xsource/p4/followup.py`.

**Preconditions:** same as `request.outreach` plus at least one replied shortlist entry on the chosen request.

**Mutation risk and gate:** identical to `request.outreach`.

**Target live path:** current implementation is the target state.

---

### 5c · `watcher.status` — live read-only walk

Open shelf `E`, item `3` (Reply watcher), then continue through the read-only preflight.
The screen lists each open request and when the watcher last checked it. The summary gives
how many requests are watched and the latest check, or "never" if none has been checked.
Closed requests are excluded. Corrupt records are reported in the summary.

The rows match `xsource watcher status`, which prints the open-request count followed by
request ids and their last-check timestamps. Neither view reports a thread count, backlog
or GCS heartbeat. Both use `watcher_status_rows` in `src/xsource/cli/cockpit.py`.

**Preconditions:** the request store is readable. An offline local cache is allowed;
Gmail credentials are not needed to view status.

**Mutation risk:** no request updates, drafts or outgoing messages. Loading the existing
store may refresh its local cache or quarantine corrupt lines.

**Target live path:** implemented by the [watcher status plan](superpowers/plans/2026-09-23-watcher-status-card.md).

---

## Journey 6 — Diagnostics (shelf G)

**Entry point:** `G` or `g` → doctor screen (bypasses shelf menu — opens directly)

### 6a · `doctor` — live (framework-integrated)

**Current state:** doctor screen is fully implemented via framework host hooks.
Code path: `doctor_build_report` → `doctor_build_probes` (9 probes: Maps key,
Anthropic key, Sheets token, Store, Budget, Home postcode, Store records, Reply watcher,
Pending signals).
The capability entry has `run=None` because doctor is invoked by the framework directly
(pressing G), not via a cockpit walk handler.

**Preconditions:** none required to open; probes report individually what is missing.

**Mutation risk:** read-only — no mutations.

"Store records" counts suppliers, requests and invoices. "Reply watcher" uses the same
staleness rule as the fleet signal: it is red when live outreach threads exist and no open
request has been checked within the last two hours. Check the watcher job and its logs;
this warning alone does not establish why checks have stopped.

"Pending signals" counts items currently raised by the horizon scan, rather than a stored
queue. Amber means there are items to review. The detail shows whether emission is enabled;
it does not confirm delivery. These probes have no automatic fixes and do not emit signals.

**Target live path:** implemented by the [watcher status plan](superpowers/plans/2026-09-23-watcher-status-card.md).

---

## Follow-up scoping

The table below records completed improvements and the remaining suggested work.

| # | Capability | Target | Size | Notes |
|---|---|---|---|---|
| 1 | `watcher.status` | Cockpit card wired to live watcher state | S | Built: [watcher status plan](superpowers/plans/2026-09-23-watcher-status-card.md); shared CLI rows and structured frames |
| 2 | `request.sync` | Sync walk in cockpit + `--dry-run` on `sync-all` | M | Two sub-tasks: cockpit walk (read path preview + confirm-apply) and CLI `--dry-run` flag |
| 3 | `doctor` | Add store counts + watcher + signal count to probes | XS | Built: [watcher status plan](superpowers/plans/2026-09-23-watcher-status-card.md); three read-only probes |
| 4 | `partner.checkatrade` | Checkatrade walk under guarded-apply gate | L | Requires operator DPA sign-off; gate token handshake; post path scoped carefully |
