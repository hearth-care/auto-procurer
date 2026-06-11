"""Guard against regression of the clonway-cockpit pin to a branch ref.

A branch-name pin (e.g. rev = "main") means any framework push can silently
break this worker.  This test enforces that the rev is either:
  * a full 40-character hex SHA (the current form), or
  * a semantic version tag of the form vX.Y.Z (for when the framework gets tags).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TAG_RE = re.compile(r"^v\d+\.\d+")


def test_clonway_cockpit_pin_is_sha_or_tag():
    data = tomllib.loads(PYPROJECT.read_text())
    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    cockpit = sources.get("clonway-cockpit", {})
    rev = cockpit.get("rev", "")
    assert rev, "clonway-cockpit source entry is missing a 'rev' field"
    ok = bool(_SHA_RE.match(rev)) or bool(_TAG_RE.match(rev))
    assert ok, (
        f"clonway-cockpit rev={rev!r} is a branch name, not a SHA or tag. "
        "Use a full 40-char commit SHA (or a vX.Y.Z tag once the framework ships them). "
        "See CLAUDE.md 'Bumping the framework pin' for the procedure."
    )
