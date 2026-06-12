"""Parity gate: every non-empty equivalent_cli in the cockpit names a parseable command.

Two checks:
1. Capability registry — every CapabilitySpec.equivalent_cli that is not None/empty
   invokes with --help and exits 0 against the Typer app.
2. Walk preflight drive — opening request.new and request.outreach in agent mode
   emits a preflight frame whose equivalent_cli is NOT a nonexistent command.

These two checks together close the gap that caused PR #17: a fictional CLI string
that looked plausible but exited 2 when the operator followed the hint.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from clonway_cockpit import registry, shell
from clonway_cockpit.agent import _NullScreen
from typer.testing import CliRunner

from xsource.cli import app, cockpit

_runner = CliRunner()
_FICTIONAL = {
    "xsource request new",
    "xsource request outreach",
}


def _parseable_cli_strings() -> list[str]:
    """Collect non-None, non-empty equivalent_cli values from the capability registry."""
    cockpit.register_all()
    return [
        c.equivalent_cli
        for c in registry.get_capabilities()
        if c.equivalent_cli  # skip None and ""
    ]


def _preflight_equivalent_cli(cap_key: str) -> str | None:
    """Drive into a walk preflight in agent mode and return its equivalent_cli."""
    host = cockpit._host(agent_mode=True)
    host.on_open()
    stream: list = []
    patched = replace(host, on_screen=stream.append)
    shell._open_capability(patched, cap_key, _NullScreen(), lambda: "q")
    for frame in stream:
        if frame.kind == "walk.preflight":
            return frame.meta.get("equivalent_cli")
    return None


@pytest.mark.parametrize("cli", _parseable_cli_strings())
def test_equivalent_cli_parses(cli: str) -> None:
    """Each equivalent_cli in the capability registry exits 0 with --help.

    Strip the leading 'xsource' token: CliRunner invokes against app which IS xsource.
    """
    tokens = cli.split()
    # equivalent_cli strings are written as full shell commands ("xsource request sync").
    # CliRunner invokes against the `app` object which IS the xsource binary, so drop
    # the leading "xsource" token before invoking.
    if tokens and tokens[0] == "xsource":
        tokens = tokens[1:]
    result = _runner.invoke(app, tokens + ["--help"])
    assert result.exit_code == 0, (
        f"equivalent_cli={cli!r} does not parse: exit {result.exit_code}\n{result.output}"
    )


@pytest.mark.parametrize("cap_key", ["request.new", "request.outreach"])
def test_cockpit_only_walk_preflight_carries_no_fictional_cli(cap_key: str) -> None:
    """Driving request.new and request.outreach to preflight: no stale fictional command."""
    cli = _preflight_equivalent_cli(cap_key)
    assert cli not in _FICTIONAL, f"{cap_key} preflight still emits stale equivalent_cli={cli!r}"
