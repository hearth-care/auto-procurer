# CLAUDE.md — Auto-Procurer (xsource)

Worker-specific rules for xsource. The global `~/.claude/CLAUDE.md` and the `clonway-cockpit`
framework rules (incl. agent-navigability) apply in every session and are not restated here.
xsource is a live worker: procurement research → shortlist Sheet → draft-only
outreach and follow-ups → reply watcher → sheet sync → invoice capture/handoff,
plus horizon Signal builders, running as Cloud Run jobs (see README "Runtime").

## Domain rules

- **Draft-never-send:** outreach surfaces create Gmail drafts and record ids;
  nothing in this repo sends email (`tests/test_no_send_endpoints.py` is the gate).
- **Single write gate:** every mutating cockpit walk routes through the framework
  `confirm_apply`; agent mode (`--agent-stdio`) is dry-run without `--allow-apply`.
- **Public repo:** no real supplier names/ids, personal emails, internal hostnames,
  or machine-local paths in docs or examples.
- **Cockpit tests drive frames, not text:** assert structured `ScreenModel` frames
  (`CockpitDriver`) or registry data — never `export_text()` scraping
  (`tests/test_cockpit_placeholders.py` shows the pattern).

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
