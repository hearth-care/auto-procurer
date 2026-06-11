# [Plan] P4 completion: triggers end-to-end + recurring reorder actions

**Status:** implemented (2026-06-11)
**Source:** fleet audit 2026-06-11, items S10, S7
**Wave:** 2 (S10), 4 (S7)

P4 was shipped as stubs: the logic modules exist and are unit-tested, but the
capabilities that expose them are registered with `run=None`, their
`equivalent_cli` strings name commands that do not exist, and nothing converts
a parsed trigger or a recurring-consumable signal into an actual request. This
plan wires trigger parsing end-to-end with real tests (S10) and gives
recurring-consumable signals their missing action — a prefilled, operator-
reviewed reorder flow (S7) — without loosening the draft-only/never-order
posture.

## Why

Every claim was re-verified against `origin/main` (`ebfd22a`) on 2026-06-11.

### S10 — P4 capabilities are registered but dead

- `src/xsource/cli/cockpit.py:416-444` — `request.trigger` ("Convert an
  approved email/chat trigger into request.new input"), `request.followup`,
  and `partner.checkatrade` are registered via the bulk loop that sets
  `run=None`. They render in the cockpit as capabilities an agent or operator
  can see, but activate nothing.
- The advertised CLI equivalents are fictional: `xsource request trigger` and
  `xsource request followup` do not exist — `src/xsource/cli/request.py`
  defines only `sync` and `sync-all`; there is no `partner` sub-app at all
  (`src/xsource/cli/__init__.py` mounts `signals`, `watcher`, `request`).
- The parsing logic itself is real but shallow-tested:
  `src/xsource/p4/triggers.py:27` — `parse_trigger` keyword-matches
  `_PROCUREMENT_HINTS` (line 8) and returns a `ParsedTrigger(kind="request.new",
  raw_need=<body>, constraints={"source": ...})`. `tests/p4/test_triggers.py`
  has exactly two unit cases (one accept, one reject). Nothing tests — or
  implements — the journey from an email/chat payload to a populated
  `request.new` walk, even though the walk seam exists
  (`src/xsource/cli/cockpit.py:152-160` `_need_step` builds the same
  `raw_need` + `constraints` bag shape, and `src/xsource/walks/request_new.py`
  applies it).
- Follow-up drafting is likewise orphaned: `src/xsource/p4/followup.py` —
  `create_followup_draft` builds a draft via the same draft-only client used by
  outreach and stamps `followup_*` metadata on the shortlist entry, but no CLI,
  walk, or capability reaches it.

### S7 — recurring-consumable signals have no action

- `src/xsource/signals/build.py:133-165` — `build_recurring_service_signals`
  emits `deadline.approaching` when a supplier with `recurs_every_months` and
  `last_used` (models.py:36, 33) comes due inside a 21-day horizon. Its
  `capability_key` is `"book.search"` (line 159) — i.e. the "action" offered
  for "your recurring service is due" is *a search screen*. The operator must
  manually re-create the request, re-pick the supplier, and re-guess the price.
- The data to prefill a reorder already exists on the records:
  `Supplier.preferred` / `preferred_set` (`src/xsource/store/models.py:30-31`),
  `Supplier.price_history` (line 34, including `"used"` outcomes from
  `src/xsource/sheet/sync.py:60-70`), and the supplier's categories/tags.
- The fleet audit calls this out as the worker's pattern: proactive signals are
  implemented (this worker is one of only two with a real horizon scan), but
  the *reactive half* — turning a signal into prefilled work — is missing.

### Safety context (what must not change)

- Outreach is structurally draft-only: `tests/test_no_send_endpoints.py` and
  `tests/test_safety.py` enforce the never-send posture; the outreach client is
  a draft-only wrapper.
- `src/xsource/p4/checkatrade.py` builds signed partner-lead requests but never
  posts; its docstring pins posting behind the cockpit apply gate. This plan
  keeps it build-only.

## Scope

In scope:

- real `run=` handlers (walks) and real CLI commands for `request.trigger` and
  `request.followup` (S10)
- end-to-end trigger tests: payload → parse → prefilled walk → request created,
  with mocked research/Sheets (S10)
- a reorder flow: recurring signal → prefilled `request.new` (preferred
  supplier + historical budget) → operator review → draft-only outreach (S7)
- repointing recurring signals at the new reorder capability (S7)

Out of scope:

- a live inbound feed of email/chat triggers (fleet-side: the mail worker's
  classified-inbound routing is the planned producer; until then triggers
  arrive as operator-pasted/file payloads)
- Checkatrade posting (stays build-only behind the gate; enabling it is its own
  decision with the operator)
- auto-creating or auto-sending anything: every flow below ends in an operator
  review step and, at most, Gmail *drafts*

## Spec

### Trigger wiring (S10)

- **CLI:** `xsource request trigger` accepting `--file <json>` (and stdin), the
  payload being the documented `{source, subject?, body}` shape that
  `parse_trigger` already consumes. Non-procurement payloads exit with a clear
  "not a procurement trigger" message and status 1.
- **Walk:** `request.trigger` gets a real handler that runs `parse_trigger`,
  shows what was extracted (source, raw need), lets the operator amend the
  need text, then *enters the existing `request.new` step chain* (triage →
  research → review/apply) with the bag pre-seeded — one walk, no duplicated
  steps. The trigger source is recorded in `request.constraints["source"]` so
  provenance survives into the store.
- **Followup:** `xsource request followup <request-id> <supplier-id>` and a
  walk handler for `request.followup` that lists replied shortlist entries,
  lets the operator pick one, previews the body, and creates the draft via the
  existing draft-only client behind `confirm_apply`. (`create_followup_draft`
  is reused as-is; the operator identity line in the body template should come
  from config, not a hardcoded name — fix while wiring.)
- **Honest registration:** capabilities whose handlers are not yet shipped must
  not advertise fictional CLI strings. As part of this work, `register_all`
  stops claiming `equivalent_cli` for anything that `xsource --help` cannot
  back; `partner.checkatrade` is annotated as gated/build-only.

### End-to-end tests (S10)

- `tests/p4/test_trigger_e2e.py`:
  - email payload → `parse_trigger` → walk bag → (mocked gateway triage, mocked
    research fns, fake Sheets/store) → a `Request` exists in the store with the
    trigger's `raw_need`, `constraints["source"] == "email"`, and a shortlist;
  - chat payload rejection: walk exits at step 1 with no store writes;
  - CLI: `request trigger --file` round-trip via Typer's runner.
- Followup tests: draft created only after confirm; `followup_*` metadata
  stamped; declining the confirm leaves no draft (mirror the existing outreach
  draft tests in `tests/outreach/test_drafts.py`).

### Reorder flow (S7)

New module `src/xsource/p4/reorder.py` + capability `request.reorder`:

1. **Entry:** from the recurring signal (its `capability_key` and `focus`
   change to `request.reorder` / `<supplier_id>`), from the cockpit shelf, or
   `xsource request reorder <supplier-id>`.
2. **Prefill (pure function, unit-testable):** given the supplier and the
   request history, build a `ReorderProposal`:
   - `raw_need`: derived from the supplier's most recent `"used"` request
     (`price_history` row → `request_id` → `Request.raw_need`), falling back
     to the supplier's primary category;
   - preferred supplier pinned at shortlist rank 1 (respecting
     `preferred`/`preferred_set`);
   - budget hint: median of that supplier's historical amounts for the
     category, shown as guidance in the review step and recorded in
     `constraints["budget_hint"]`;
   - cadence context: when it was last done, when it's due.
3. **Review:** the operator sees the proposal and chooses: (a) reorder from the
   incumbent — skip research, go straight to the review/apply step of
   `request.new` with a one-entry shortlist; or (b) re-tender — run the full
   research step with the incumbent guaranteed a shortlist slot for
   comparison; or (c) dismiss.
4. **Apply:** exactly the existing `request.new` apply path (Sheet + store via
   `confirm_apply`), then optionally straight into the existing draft-only
   outreach walk. **Nothing is ordered, sent, or committed to a supplier at any
   point — the flow ends at Gmail drafts the operator must send themselves.**
5. **Dedup:** an open request created from a reorder records
   `constraints["reorder_supplier_id"]`; the recurring-signal builder skips
   suppliers that already have such an open request, so the signal stops
   re-firing once acted on.

## Implementation plan

### Phase 1 — trigger CLI + walk (Wave 2, M)

- [x] `src/xsource/cli/request.py`: `trigger` command (`--file`/stdin JSON).
- [x] `src/xsource/cli/cockpit.py`: real handler for `request.trigger` that
      pre-seeds the `request.new` step chain; remove fictional
      `equivalent_cli` claims from still-stubbed capabilities.
- [x] `tests/p4/test_trigger_e2e.py` as specced (no live credentials; all
      collaborators injected at the existing seams).
- Tests: e2e accept + reject paths; CLI exit codes; provenance recorded.

### Phase 2 — followup wiring (Wave 2, S)

- [x] `src/xsource/cli/request.py`: `followup` command.
- [x] `src/xsource/cli/cockpit.py`: handler for `request.followup` behind
      `confirm_apply`; blast-radius text mirrors the outreach capability's.
- [x] `src/xsource/p4/followup.py`: operator identity from config.
- Tests: confirm/decline paths; metadata stamping; draft-only client used.

### Phase 3 — reorder proposal engine (Wave 4, M)

- [x] `src/xsource/p4/reorder.py`: `build_reorder_proposal` (pure) + plumbing.
- [x] `tests/p4/test_reorder.py`: prefill correctness (need derivation, rank-1
      pinning, budget median, missing-history fallbacks).

### Phase 4 — reorder capability + signal repoint (Wave 4, M)

- [x] `request.reorder` capability + walk (reorder vs re-tender vs dismiss).
- [x] `src/xsource/signals/build.py`: recurring signals point at
      `request.reorder`; skip suppliers with an open reorder request.
- [x] Cockpit render/model parity suite extended to the new screens.
- Tests: signal capability_key/focus; dedup-on-open-request; both walk
  branches end at the standard apply gate; no new send paths
  (`tests/test_no_send_endpoints.py` still green).

## Acceptance criteria

- [x] `xsource request trigger` exists and a procurement-shaped payload drives
      the full walk to a stored request in tests, with provenance recorded.
- [x] Non-procurement payloads are rejected with no store writes.
- [x] `request.trigger`, `request.followup`, and `request.reorder` have real
      handlers; no registered capability advertises a CLI command that
      `xsource --help` cannot show.
- [x] A due recurring supplier yields a signal that opens a prefilled reorder
      review (incumbent at rank 1, budget hint from price history), and acting
      on it stops the signal re-firing.
- [x] Both reorder branches end at the existing confirm-apply gate; outreach
      remains draft-only; the structural no-send tests are untouched and green.
- [x] Checkatrade remains build-only; no posting path is added.

## Risks & dependencies

- **Trigger quality:** `_PROCUREMENT_HINTS` keyword matching will both
  over- and under-trigger on real text. Acceptable for an operator-confirmed
  flow (a human reviews before anything happens); revisit with an LLM
  classification step only if false negatives annoy in practice — and note
  that inbound text reaching an LLM raises the fleet's known prompt-injection
  concern, so keep the keyword gate in front.
- **Inbound feed dependency:** the real trigger producer (classified-inbound
  routing from the mail worker) is a Wave-3 fleet item in another repo. This
  plan's payload shape should be agreed with that work so the file/stdin format
  becomes the wire format later.
- **Walk-chaining seam:** pre-seeding the `request.new` chain must reuse its
  `Step` list rather than copying steps; if the framework's walk API at the
  pinned rev makes composition awkward, prefer refactoring `request_new`'s
  steps into a shared list over duplicating them.
- **Reorder need derivation:** the most recent request's text may be stale or
  wrong; the review step always shows it editable, never auto-applies.
- **Budget hints from sparse history:** medians over one or two data points are
  weak; label the hint with its sample size.

## Next-agent pickup

1. Branch off `main`; do not stack on this planning branch.
2. Re-verify the citations above against current `main` (the repo moved during
   the audit window).
3. Phases 1–2 (S10, Wave 2) are independent of Phases 3–4 (S7, Wave 4) — ship
   them as separate PRs; Phase 4 depends on Phase 3 only.
4. Run `uv run pytest -q`, `uv run ruff check .`, `uv run mypy` before each PR;
   the cockpit render/model parity contract test must stay green when adding
   screens.
5. Public repo: fixture payloads and examples use invented suppliers and
   needs — no real business specifics.

## HANDOFF NOTES

**Phase:** all 4 phases implemented; QA follow-up gate fixes complete on this PR branch.
**Current agent:** fixer-codex-20260611T215153Z-55255.

### What was built

- **Phase 1 (S10):** `xsource request trigger --file <json>` CLI; `_trigger_step` +
  `_request_trigger_handler` in cockpit.py; trigger parse → triage → research → apply walk;
  `tests/p4/test_trigger_e2e.py` (walk step chain + CLI round-trip tests).

- **Phase 2 (S10):** `xsource request followup <request-id> <supplier-id>` CLI;
  `_followup_select_step` + `_followup_apply_step` + `_request_followup_handler` in cockpit.py;
  `operator_name` parameter added to `create_followup_draft` (no more hardcoded "Milo");
  `Config.operator_display_name` from `XSOURCE_OPERATOR_DISPLAY_NAME` env var;
  `tests/p4/test_followup_wiring.py`. QA follow-up fix: both CLI and cockpit now
  preview the exact follow-up body before creating a Gmail draft; the cockpit lists only
  replied shortlist entries; the CLI decline path exits without touching Gmail.

- **Phase 3 (S7):** `src/xsource/p4/reorder.py` — `ReorderProposal` dataclass +
  `build_reorder_proposal` pure function; `tests/p4/test_reorder.py` (11 unit tests).

- **Phase 4 (S7):** `request.reorder` capability + 3-step walk (proposal → research → apply);
  `xsource request reorder <supplier-id>` CLI; `build_recurring_service_signals` now:
  (a) emits `capability_key="request.reorder"` instead of `"book.search"`,
  (b) accepts optional `requests` arg and skips suppliers with open reorder requests
  (dedup on `constraints["reorder_supplier_id"]`);
  `tests/p4/test_reorder_capability.py`.

- **Honest registration:** removed fictional `equivalent_cli` from `request.list`,
  `book.search`, `book.import`, `book.publish`, `partner.checkatrade`, `doctor`.
  Only capabilities with real CLI commands claim one.

### Deviations from plan

- "Cockpit render/model parity suite extended to the new screens" — the new walk
  handlers do not add any bespoke `render_*` functions; they use framework-provided
  step rendering. The existing `test_render_model_parity` test passes vacuously
  (correct per the contract test's docstring: "Vacuously true for the scaffold").

- Earlier handoff notes said `xsource request reorder <supplier-id>` did not focus the
  reorder capability. That was fixed by the previous QA-fix commit on this branch:
  `run_cockpit(focus=...)` now deep-links to `request.reorder:<supplier_id>`.

### Latest gates

- `uv run pytest tests/p4/test_followup_wiring.py -q` -> 7 passed
- `uv run pytest tests/p4 -q` -> 40 passed
- `uv run pytest -q` -> 202 passed
- `uv run ruff check .` -> All checks passed
- `uv run mypy` -> Success: no issues found in 56 source files
- `pre-commit run --all-files` -> skipped because `.pre-commit-config.yaml` is not a file

### Next concrete step

- Mark the PR ready, move the label from `agent:claimed` to `agent:needs-qa`, post the
  completion comment with the gate evidence, and remove the worktree.
