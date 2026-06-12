# xsource cockpit journey map

**Last verified:** 2026-06-12 against `origin/main` (`354fd63`).

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

### 2a · `request.list` — placeholder

**Current state:** `run=None` — renders a static card only.
No live data view exists in the cockpit.

**Preconditions:** none (card is always reachable).

**Mutation risk:** read-only — no mutations.

**Target live path:** card wired to a read-only list of open and recent requests from the
GCS store; agent-model twin required per `CLAUDE.md` parity rule.

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

### 3a · `book.search` — placeholder

**Current state:** `run=None` — renders a static card only.
A real search implementation exists at `src/xsource/book/search.py` (`find_matches`).
The function is already called internally by `request.new` research.

**Preconditions:** GCS store reachable (for live data); read-only without store.

**Mutation risk:** read-only — no mutations.

**Target live path:** card wired to `find_matches` with a text/category/tag query input;
read path only, no writes.

---

### 3b · `book.import` — placeholder

**Current state:** `run=None` — renders a static card only.
A real importer exists at `src/xsource/book/importer.py`.

**Preconditions:** GCS store reachable; CSV file path provided.

**Mutation risk:** writes new supplier records to the GCS store.
Gate: confirm-apply required before writing.

**Target live path:** card wired to the importer with a file-path input step; read path
(preview count) before apply.

---

## Journey 4 — Publish (shelf D)

**Entry point:** shelf `D` → `book.publish`, `partner.checkatrade`

### 4a · `book.publish` — placeholder

**Current state:** `run=None` — renders a static card only.
A real publish module exists at `src/xsource/book/publish.py`.

**Preconditions:** GCS store reachable; Drive token present.

**Mutation risk:** regenerates the read-only staff supplier directory (write to Drive/Sheets).
Gate: confirm-apply required.

**Target live path:** card wired to the publish module; read-only preview (record count) before apply.

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

### 5c · `watcher.status` — placeholder card / live CLI

**Current state:** `run=None` — cockpit card is a static reference only.
The CLI path (`xsource watcher status`) is fully implemented.
Code path: `src/xsource/cli/watcher.py` → `src/xsource/watcher/state.py`.

The CLI prints thread count, pending-reply backlog, last-seen timestamp, and heartbeat.
The Reply watcher daemon (`xsource watcher start`) runs as a launchd service.

**Preconditions:**

| Precondition | Source |
|---|---|
| `XSOURCE_GMAIL_TOKEN_PATH` | OAuth token — thread polling |
| GCS store reachable | reads watcher state |

**Mutation risk:** read-only — no mutations.

**Target live path:** cockpit card wired to the real watcher state the CLI already prints,
including thread list, pending-replies backlog, and heartbeat timestamp.

---

## Journey 6 — Diagnostics (shelf G)

**Entry point:** `G` or `g` → doctor screen (bypasses shelf menu — opens directly)

### 6a · `doctor` — live (framework-integrated)

**Current state:** doctor screen is fully implemented via framework host hooks.
Code path: `doctor_build_report` → `doctor_build_probes` (6 real probes: Maps key,
Anthropic key, Sheets token, Store, Budget, Home postcode).
The capability entry has `run=None` because doctor is invoked by the framework directly
(pressing G), not via a cockpit walk handler.

**Preconditions:** none required to open; probes report individually what is missing.

**Mutation risk:** read-only — no mutations.

**Target live path:** current implementation covers auth, config, and store readiness.
Future extension: add store record counts, watcher heartbeat, and pending-signal count
to give one combined health surface without needing multiple CLI commands.

---

## Follow-up scoping

The table below maps each unbuilt target path to a rough size and suggested ordering.

| # | Capability | Target | Size | Notes |
|---|---|---|---|---|
| 1 | `request.list` | Read-only list view from GCS store | S | Needs model twin (render + model parity); read path only, no mutations |
| 2 | `watcher.status` | Cockpit card wired to live watcher state | S | Reuse `xsource watcher status` data; card + model twin; no new logic |
| 3 | `request.sync` | Sync walk in cockpit + `--dry-run` on `sync-all` | M | Two sub-tasks: cockpit walk (read path preview + confirm-apply) and CLI `--dry-run` flag |
| 4 | `book.search` | Search walk wired to `find_matches` | S | `find_matches` already exists; walk = one input step + results table + model twin |
| 5 | `book.import` | Import walk with CSV preview then apply | M | File-path input → read preview count → confirm-apply → write; needs model twin |
| 6 | `book.publish` | Publish walk wired to `book/publish.py` | M | Preview record count → confirm-apply → write; confirm-apply gate required |
| 7 | `doctor` | Add store counts + watcher + signal count to probes | XS | Extend `doctor_build_probes`; no new screens or walks required |
| 8 | `partner.checkatrade` | Checkatrade walk under guarded-apply gate | L | Requires operator DPA sign-off; gate token handshake; post path scoped carefully |
