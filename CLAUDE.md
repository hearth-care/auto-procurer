# CLAUDE.md — Auto-Procurer (xsource)

Worker-specific rules for xsource. The Clonway-family + global CLAUDE.md rules layer
on top; this file adds what is specific to this worker. Fill in domain rules (integrations,
safety invariants, region/PII posture) as the worker grows.

## Agent-navigability is non-negotiable

Every autoworker is simultaneously a human TUI and an agent-drivable surface — same binary,
same code path. This is enforced, not aspirational:

- **Every page-framing `render_*` ships a `model_*` twin.** CI runs
  `clonway_cockpit.contract.assert_render_model_parity(<your render ns>)` (see
  `tests/test_cockpit_contract.py`). A screen with no model hands an agent `unstructured` —
  that fails the build.
- **Drive, don't scrape.** Verify the cockpit via `xsource --agent-stdio` /
  `clonway_cockpit.agent.CockpitClient` / `CockpitDriver`. Never assert on `export_text()`.
  The drive-it conformance test (`assert_drives_clean`) proves every modeled screen emits on
  a real path.
- **Money/write paths go through the gate.** Agent mode is dry-run by default; posting
  requires the explicit guarded-apply token handshake (`--allow-apply`). Never add a second
  post path.
- **The protocol is versioned.** Frames carry `schema_version`; a breaking change bumps it.

See clonway-cockpit `docs/agent-screen-model.md` for the full protocol + the wiring recipe.

## Bumping the framework pin

`pyproject.toml → [tool.uv.sources] → clonway-cockpit → rev` must always be a full
40-character commit SHA (or a `vX.Y.Z` tag once the framework publishes releases).
`tests/test_dependency_pins.py` fails CI if a branch name is committed.

**Procedure:**

1. Pick the target commit SHA from `hearth-care/clonway-cockpit`.
2. Update `rev` in `pyproject.toml`.
3. Run `uv lock` to regenerate `uv.lock`.
4. Run `uv run pytest -q` — full local suite must be green.
5. Note the framework delta (commits included) in the PR body.
6. Commit `pyproject.toml` + `uv.lock` together in one commit.
