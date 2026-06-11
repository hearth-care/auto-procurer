# [Plan] Hygiene + watcher resilience

**Status:** implemented 2026-06-11 by builder-claude-20260611T171333Z-89967
**Source:** fleet audit 2026-06-11, items S1, S2, S3, S4, S8, S9
**Wave:** 0 (S1), 1 (S9), 2 (S2, S3, S4, S8)

This plan bundles the hygiene and resilience items from the 2026-06-11 fleet audit
into one coherent piece of work: make the dependency pin tamper-proof, make the
reply watcher survive real-world failure modes, give the LLM gateway a fallback
chain, stop the offline store cache from losing data silently, surface the
pending-replies backlog in the cockpit, and let mypy actually see the framework.

## Why

Every claim below was re-verified against `origin/main` (`ebfd22a`) on 2026-06-11.

### S1 — cockpit pin (partially resolved; guard still missing)

The audit found `clonway-cockpit` pinned to `rev = "main"`, meaning any framework
push could break this worker without a single local change. As of commit
`ebfd22a` (2026-06-11) the pin is a full commit SHA (`pyproject.toml:31`).
What is still missing:

- nothing prevents a future edit from regressing the pin to a branch ref;
- there is no documented pin-bump procedure (when, how, what to re-run);
- the SHA is opaque — the framework has no tags/changelog yet (a framework-side
  audit item), so a tag pin is a follow-up once that lands.

### S2 — watcher has no retry/backoff, no circuit breaker, no liveness test

- `src/xsource/watcher/loop.py:10-25` — `run_loop` retries at a fixed cadence
  forever. On exception it calls `on_error` and immediately re-enters the next
  cycle after the same fixed sleep.
- `src/xsource/cli/watcher.py:86` — the production `on_error` just echoes to
  stderr, which for the local daemon means a log file nobody watches. A
  persistently failing dependency (expired token, API quota, network outage)
  becomes a 60-second hot loop hammering the failing API indefinitely.
- **Loss-ordering hazard:** `src/xsource/watcher/daemon.py:148` marks a message
  processed in the SQLite dedup store *before* `daemon.py:159` persists the
  updated request. If that upsert raises (e.g. `StoreOffline`,
  `src/xsource/store/remote.py:34-36`), the parsed reply is dropped and the
  message is permanently skipped on every later cycle.
- **Test gap:** `tests/watcher/test_loop.py` drives `run_loop` with a toy
  callable; `tests/watcher/test_daemon.py` drives `process_once` with hand-rolled
  fakes. Nothing exercises the wired cycle (`cli/watcher.py:_process_factory`,
  line 49) end-to-end, so a wiring regression (env var name, store construction,
  gateway laziness) would only surface in production.

### S3 — single Anthropic model, no fallback

- `src/xsource/cli/cockpit.py:167` — `_AnthropicStructuredGateway` resolves one
  model from `XSOURCE_RESEARCH_MODEL` with a hardcoded default.
- `src/xsource/wiring.py:41` — the research searcher pins the same single model.
- Any model-side failure (model retired, overloaded, transient 5xx) fails the
  triage/research/parse step outright. There is no retry and no fallback model.

### S4 — GCS offline cache silently stops persisting new data

- `src/xsource/store/remote.py:41-47` — `make_blob` swallows *every* exception
  (missing credentials, network down, library import failure) and returns
  `None`, putting the store into offline read-only mode.
- Reads keep serving the stale local cache; `upsert` raises `StoreOffline`
  (`remote.py:34-36`).
- The cockpit shows a warn-level "store offline" pill
  (`src/xsource/cli/cockpit.py:520-524`) and a Doctor probe, but neither says
  the operational truth: **new suppliers, new requests, and parsed replies are
  not being saved**. The watcher daemon has no store precondition at all — it
  keeps cycling, and combined with the S2 ordering hazard, loses data.

### S8 — pending-replies backlog invisible in the cockpit

- `capture_state` (`src/xsource/cli/cockpit.py:459`, pills at 506-525) exposes
  four pills: black book, open requests, research budget, store. The watcher's
  `possible_replies` queue — off-thread supplier replies flagged
  `needs_review` by `daemon.py:_flag_possible_replies` — appears nowhere, so a
  growing review backlog is silent until someone opens an individual request.

### S9 — mypy cannot see the framework

- `pyproject.toml:62` — `ignore_missing_imports = true` is a *global* blanket.
  It silences not just genuinely untyped third parties but the entire
  `clonway_cockpit` import surface, so a framework API drift (exactly the S1
  failure mode) type-checks clean here.

## Scope

In scope:

- pin regression guard + documented bump procedure (S1 remainder)
- watcher exponential backoff, circuit breaker, persist-before-mark fix, and a
  two-cycle end-to-end liveness test (S2)
- env-configurable Anthropic model fallback chain (S3)
- offline-store operator warning: error-level pill wording, watcher
  precondition, and an `anomaly.detected` signal (S4)
- pending-replies backlog pill (S8)
- targeted mypy configuration + framework type visibility (S9)

Out of scope:

- framework-side release tags/changelog (framework repo item; tracked there)
- Cloud Run migration of the watcher (separate plan:
  `2026-06-fleet-audit-cloud-run-migration.md`)
- invoice/AP work and P4 completion (separate plans in this series)

## Spec

### Pin guard (S1)

- A unit test parses `pyproject.toml` and asserts the `clonway-cockpit` source
  `rev` matches a full 40-char SHA (or, later, a `vX.Y.Z` tag) — and is not a
  branch name.
- `CLAUDE.md` gains a short "bumping the framework pin" section: pick rev, run
  `uv lock`, run the full suite, note the framework delta in the PR body.

### Watcher resilience (S2)

- `run_loop` grows backoff parameters: on consecutive failures, sleep
  `min(poll_seconds * 2**n, max_backoff_seconds)`; reset on success.
- Circuit breaker: after `N` consecutive failures (default 10), stop cycling,
  emit a watcher-down event via `xsource.obs`, and exit non-zero so the
  supervisor (launchd today, Cloud Run later) restarts visibly rather than
  spinning silently. Defaults env-tunable via `Config`.
- Persist-before-mark: in `process_once`, the request upsert moves ahead of (or
  is checkpointed with) `state.mark_processed`, so a failed persist never
  strands a message id in the dedup store.
- Liveness test: a single test wires the real `process_once` through the real
  loop for **two mocked cycles end-to-end** — fake Gmail/Sheets/gateway/store
  injected at the factory seam — asserting cycle 1 parses and persists, cycle 2
  is idempotent, and heartbeats advance.

### Model fallback chain (S3)

- New env knob (e.g. `XSOURCE_MODEL_CHAIN`, comma-separated, first entry =
  primary) consumed by both `_AnthropicStructuredGateway` and the research
  searcher wiring; `XSOURCE_RESEARCH_MODEL` stays honoured as the single-model
  override for backwards compatibility.
- On model-unavailable / overloaded / 5xx errors, try the next model in the
  chain; raise only after the chain is exhausted. Log each fallback via
  `xsource.obs` so silent quality drift is observable.
- Non-retriable errors (auth, bad request) fail fast — fallback is for
  availability, not for masking bugs.

### Offline-store warning (S4)

- Pill: when offline, level becomes `error` and the detail states that new data
  is not persisting (not just "offline").
- Watcher: a store-online check at cycle start; when offline, skip mutating
  work, log loudly, and count toward the circuit breaker rather than processing
  messages it cannot persist.
- Signal: `build_watcher_health_signals`-style `anomaly.detected` entry when
  the store is offline so the fleet briefing sees it.
- `make_blob` keeps its graceful degrade (local dev must work credential-less)
  but records *why* it degraded so Doctor can show the cause.

### Backlog pill (S8)

- New pill counting `needs_review` entries across open requests'
  `watcher["possible_replies"]`; level `warn` when non-zero; wired into the
  existing `capture_state` (and its render/model parity test).

### Framework typing (S9)

- Replace the global `ignore_missing_imports = true` with per-module
  `[[tool.mypy.overrides]]` limited to genuinely untyped third parties.
- For `clonway_cockpit`: prefer upstream `py.typed` (framework-side ask); until
  then, a minimal local stub package covering the symbols xsource imports
  (registry, walk, state, shell, signals, obs, agent, doctor, prompts, keys,
  render, usage).
- CI stays green with mypy actually checking framework call sites.

## Implementation plan

### Phase 0 — pin guard (Wave 0, S)

- [x] Add `tests/test_dependency_pins.py`: parse `pyproject.toml`, assert the
      framework `rev` is a full SHA (regex `^[0-9a-f]{40}$`) or `^v\d+\.\d+`.
- [x] Add the pin-bump procedure to `CLAUDE.md`.
- Tests: new test fails if `rev` is set back to a branch name.

### Phase 1 — mypy visibility (Wave 1, S)

- [x] Drop the global `ignore_missing_imports` from `pyproject.toml:[tool.mypy]`.
- [x] Add `[[tool.mypy.overrides]]` for remaining untyped third parties only.
- [x] Add minimal `clonway_cockpit` stubs (or consume upstream `py.typed` if
      available at the pinned rev) so `src/xsource` type-checks clean.
- Tests: `uv run mypy` green in CI with the blanket ignore removed.

### Phase 2 — watcher resilience (Wave 2, M)

- [x] `src/xsource/watcher/loop.py`: backoff parameters + circuit breaker state;
      keep the injected `sleep_fn` seam for tests.
- [x] `src/xsource/cli/watcher.py`: thread `Config`-sourced backoff/breaker
      knobs; on breaker open, emit an obs event and exit non-zero.
- [x] `src/xsource/watcher/daemon.py`: reorder persist vs `mark_processed`.
- [x] `tests/watcher/test_loop.py`: backoff growth/reset and breaker-open cases.
- [x] `tests/watcher/test_liveness.py`: two mocked cycles end-to-end through
      the real loop + real `process_once` (parse → persist → idempotent repeat).
- Tests: simulated outage shows growing sleeps; breaker opens after N failures;
  no message is marked processed when its request fails to persist.

### Phase 3 — model fallback chain (Wave 2, S)

- [x] `Config` gains the chain knob; `cli/cockpit.py` gateway and
      `wiring.py:build_research_fns` consume it.
- [x] Retriable-error classification helper + obs event on fallback.
- [x] Tests: primary-fails→fallback-succeeds; chain exhausted raises; auth
      errors do not fall back.

### Phase 4 — offline warning + backlog pill (Wave 2, S+S)

- [x] `store/remote.py`: capture degrade reason on `make_blob` failure.
- [x] `cli/cockpit.py`: error-level offline pill wording; new pending-replies
      pill; Doctor probe shows degrade reason.
- [x] Watcher cycle-start store check + offline signal entry in
      `signals/build.py`.
- [x] Tests: pill levels/details for online, offline, and non-zero backlog;
      signal emitted when store offline with open requests; render/model parity
      suite still green.

## Acceptance criteria

- [x] A `rev = "main"` regression in `pyproject.toml` fails CI.
- [x] A persistent watcher failure produces growing sleeps, then a breaker-open
      exit with an observable event — never an indefinite fixed-rate hot loop.
- [x] No code path marks a Gmail message processed unless the request update it
      produced has been persisted.
- [x] Two-cycle liveness test exists and runs in CI without live credentials.
- [x] With the primary model unavailable, triage/parse succeeds via a fallback
      model and the fallback is logged.
- [x] An offline store is visible as an error pill that states data is not
      persisting, plus a fleet signal; the watcher does not churn messages it
      cannot persist.
- [x] The cockpit shows a pending-replies backlog count.
- [x] mypy checks framework call sites (no global `ignore_missing_imports`).

## Risks & dependencies

- **Framework tags don't exist yet** — the pin guard accepts SHAs now, tags
  later; do not block on the framework's release story.
- **Stub drift (S9):** local stubs can rot against the pinned framework rev;
  keep them minimal and prefer upstream `py.typed` as the durable fix.
- **Breaker tuning:** too-aggressive thresholds turn transient blips into
  restarts; defaults should be generous (e.g. 10 consecutive failures) and
  env-tunable.
- **Behavior change in daemon ordering** needs care with the Sheet write path
  (Sheet writes currently happen before the store persist); the liveness test
  pins the intended order.
- Interaction with the Cloud Run migration plan: exit-non-zero-on-breaker is
  designed to suit both launchd (`KeepAlive`/restart) and Cloud Run restarts.

## Next-agent pickup

All phases implemented. No follow-up branch needed.

## HANDOFF NOTES

**Phase:** DONE — all 4 plan phases + 4 QA findings addressed.
**Last push:** 2026-06-11, rebased onto origin/main.
**Gates:** 150 tests pass, mypy clean, ruff clean.

**Deviations from plan:**
- S9 stubs placed in `stubs/clonway_cockpit/` with `mypy_path = ["stubs"]`;
  upstream `py.typed` not yet available at pinned rev so local stubs used.
- `AnthropicSearcher` in `research/websearch.py` extended with `model_chain`
  parameter in addition to `_AnthropicStructuredGateway` (plan mentioned both;
  the searcher needed its own chain logic since it uses a different API path).
- `_process_factory(cfg)` now takes cfg as argument (minor refactor for
  cleaner wiring of backoff/breaker knobs).
- `_make_blob_offline_reason` variable in `make_blob` is unused (local var);
  reason stored in module-level `_offline_reasons` dict — same operational
  effect, pattern cleaner for test isolation.

**QA findings fixed (fixer-claude-20260611T181542Z-78853):**
1. Runbook delta posted on hearth-care/auto-orchestrator#196.
2. `equivalent_cli="xsource doctor"` → `"xsource"` (no CLI doctor subcommand exists;
   doctor is a cockpit screen). Signal detail updated to say "open xsource cockpit".
3. `_TAG_RE` anchored to `^v\d+\.\d+\.\d+$`; negative/positive cases added.
4. `AnthropicSearcher.extract` now emits `gateway.model_fallback` obs event on fallback;
   two new tests verify obs emission and non-retriable fast-fail.
