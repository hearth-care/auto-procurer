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

from datetime import UTC, date, datetime

from clonway_cockpit.signals.horizon import ScanHorizon, is_scan_horizon
from clonway_cockpit.signals.model import Signal

from xsource.signals.build import (
    build_chase_quote_signals,
    build_recurring_service_signals,
    build_watcher_health_signals,
    build_xsource_signals,
    scan_xsource_horizon,
)
from xsource.store.models import Request, ShortlistEntry, Supplier

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


def test_chase_quotes_signal_for_old_unanswered_asks() -> None:
    request = Request(
        id="r-0042",
        created_at="2026-05-28T12:00:00+00:00",
        raw_need="tree chipping",
        status="open",
        constraints={"needed_by": "2026-06-05"},
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                outreach={"status": "asked", "asked_at": "2026-05-28T16:00:00+00:00"},
            )
        ],
    )

    signals = build_chase_quote_signals([request], today=_TODAY, now=_NOW, chase_after_days=3)

    assert len(signals) == 1
    assert signals[0].kind == "action.required"
    assert signals[0].dedup_key == "xsource|chase|r-0042"
    assert signals[0].source_id == "r-0042"
    assert signals[0].due_at == date(2026, 6, 5)


def test_chase_quotes_suppressed_when_all_asked_entries_have_quotes() -> None:
    request = Request(
        id="r-0042",
        created_at="2026-05-28T12:00:00+00:00",
        raw_need="tree chipping",
        status="open",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                outreach={"status": "asked", "asked_at": "2026-05-28T16:00:00+00:00"},
                reply={"status": "quoted", "quote_amount": 185},
            )
        ],
    )

    assert build_chase_quote_signals([request], today=_TODAY, now=_NOW) == ()


def test_recurring_service_signal_when_due_within_21_days() -> None:
    supplier = Supplier(
        id="s-0017",
        name="Smith Heating",
        categories=["heating"],
        last_used="2025-06-15",
        recurs_every_months=12,
        price_history=[{"amount": 180, "date": "2025-06-15"}],
    )

    signals = build_recurring_service_signals([supplier], today=_TODAY, now=_NOW)

    assert len(signals) == 1
    assert signals[0].kind == "deadline.approaching"
    assert signals[0].dedup_key == "xsource|recur|s-0017"
    assert signals[0].due_at == date(2026, 6, 15)


def test_watcher_health_signal_when_open_thread_poll_is_stale() -> None:
    request = Request(
        id="r-0042",
        created_at="2026-05-28T12:00:00+00:00",
        raw_need="tree chipping",
        status="open",
        watcher={"last_checked_at": "2026-06-01T04:30:00+00:00"},
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                outreach={"thread_id": "thr-1", "status": "draft_ready"},
            )
        ],
    )

    signals = build_watcher_health_signals([request], today=_TODAY, now=_NOW)

    assert len(signals) == 1
    assert signals[0].kind == "anomaly.detected"
    assert signals[0].dedup_key == "xsource|watcher"
    assert signals[0].source_id == "watcher"
