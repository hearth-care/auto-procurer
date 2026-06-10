"""AC-C6-3 — the mandatory ``@scan_horizon`` contract.

A generated worker can't exist without a horizon scan: ``scan_xsource_horizon``
is a real, ``@scan_horizon``-tagged function, and ``build_xsource_signals``
is the composed ``(*, today, now) -> Sequence[Signal]`` callable ``emit_signals``
consumes.

The LAST test (``test_horizon_is_not_empty``) is the proactive-by-construction
gate: it ``xfail``s while the stub returns ``()`` and will PASS — flipping to an
unexpected pass — the moment you fill in real signals, prompting you to remove
the ``xfail`` marker. Until then the empty horizon is *visible*, not silent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from clonway_cockpit.signals.horizon import ScanHorizon, is_scan_horizon
from clonway_cockpit.signals.model import Signal

from xsource.signals.build import (
    build_xsource_signals,
    scan_xsource_horizon,
)

_NOW = datetime(2026, 6, 1, 7, 0, tzinfo=UTC)
_TODAY = _NOW.date()


def test_scan_horizon_exists_and_is_tagged() -> None:
    assert callable(scan_xsource_horizon)
    assert is_scan_horizon(scan_xsource_horizon)
    assert isinstance(scan_xsource_horizon, ScanHorizon)


def test_scan_horizon_returns_a_signal_set() -> None:
    out = scan_xsource_horizon(today=_TODAY, now=_NOW)
    assert all(isinstance(s, Signal) for s in out)


def test_build_signals_is_composed_horizon() -> None:
    out = build_xsource_signals(today=_TODAY, now=_NOW)
    assert isinstance(out, tuple)
    assert all(isinstance(s, Signal) for s in out)


def test_stub_horizon_is_empty_for_now() -> None:
    # Documents the scaffolded state: the stub returns (). Delete this test once
    # the horizon is filled in (the xfail below then drives you to).
    assert build_xsource_signals(today=_TODAY, now=_NOW) == ()


@pytest.mark.horizon_stub
@pytest.mark.xfail(
    reason="TODO(xsource): @scan_horizon stub returns () — fill in real "
    "forward signals, then remove this xfail.",
    strict=True,
)
def test_horizon_is_not_empty() -> None:
    # Proactive-by-construction gate. xfail (strict) while the horizon is empty;
    # the moment you emit a real signal this PASSES → XPASS → CI flags it, telling
    # you to drop the xfail. A worker with a dead horizon stays visible.
    assert build_xsource_signals(today=_TODAY, now=_NOW) != ()
