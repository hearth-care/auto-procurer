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
_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")


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


def test_tag_regex_rejects_non_semver():
    """_TAG_RE must reject prefix-only refs such as v1.2 or v1.2-main."""
    assert not _TAG_RE.match("v1.2"), "bare vX.Y prefix should not be accepted"
    assert not _TAG_RE.match("v1.2-main"), "vX.Y-suffix ref should not be accepted"
    assert not _TAG_RE.match("main"), "bare branch name should not be accepted"


def test_tag_regex_accepts_full_semver():
    assert _TAG_RE.match("v1.2.3")
    assert _TAG_RE.match("v10.20.30")
