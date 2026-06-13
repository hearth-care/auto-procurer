# CLAUDE.md — Auto-Procurer (xsource)

Worker-specific rules for xsource. The global `~/.claude/CLAUDE.md` and the `clonway-cockpit`
framework rules (incl. agent-navigability) apply in every session and are not restated here.
xsource is a stub worker: it has no domain rules yet. Add them (integrations, safety
invariants, region/PII posture) as the worker grows.

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
