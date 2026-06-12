"""AC-C6-3 — the ``@scan_horizon`` contract and the four horizon builders.

``scan_xsource_horizon`` is a real, ``@scan_horizon``-tagged function composed
from four builders: chase-quote, recurring-service, watcher-health, and
store-offline. ``build_xsource_signals`` is the composed
``(*, today, now) -> Sequence[Signal]`` callable that ``emit_signals`` consumes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from clonway_cockpit.signals.horizon import ScanHorizon, is_scan_horizon
from clonway_cockpit.signals.model import Signal

from xsource.invoices.capture import capture_invoice
from xsource.signals.build import (
    build_chase_quote_signals,
    build_invoice_variance_signals,
    build_payment_required_signals,
    build_recurring_service_signals,
    build_rejected_invoice_signals,
    build_store_offline_signals,
    build_watcher_health_signals,
    build_xsource_signals,
    scan_xsource_horizon,
)
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, ShortlistEntry, Supplier

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


def test_build_store_offline_signals_emits_when_offline_with_open_requests():
    requests = [
        Request(
            id="r-1",
            created_at="2026-06-01T00:00:00+00:00",
            raw_need="plumbing",
            status="open",
        )
    ]
    signals = build_store_offline_signals(requests, today=_TODAY, now=_NOW, store_offline=True)
    assert len(signals) == 1
    assert signals[0].kind == "anomaly.detected"
    assert signals[0].dedup_key == "xsource|store_offline"
    assert signals[0].level == "error"


def test_build_store_offline_signals_silent_when_online():
    requests = [
        Request(
            id="r-1",
            created_at="2026-06-01T00:00:00+00:00",
            raw_need="plumbing",
            status="open",
        )
    ]
    signals = build_store_offline_signals(requests, today=_TODAY, now=_NOW, store_offline=False)
    assert signals == ()


def test_build_store_offline_signals_silent_when_no_open_requests():
    signals = build_store_offline_signals([], today=_TODAY, now=_NOW, store_offline=True)
    assert signals == ()


def test_payment_required_signal_for_emittable_invoice() -> None:
    supplier = Supplier(id="s-0017", name="Smith Heating")
    invoice = InvoiceRecord(
        id="i-0001",
        request_id="r-0001",
        supplier_id="s-0017",
        amount_minor=12500,
        invoice_number="INV-100",
        invoice_date="2026-05-31",
        due_date="2026-06-03",
        description="Boiler repair",
        source="manual",
        status="captured",
    )

    signals = build_payment_required_signals([invoice], [supplier], today=_TODAY, now=_NOW)

    assert len(signals) == 1
    assert signals[0].kind == "payment.required"
    assert signals[0].title == "Invoice INV-100 - Smith Heating"
    assert signals[0].detail == "GBP 125.00 - Boiler repair"
    assert signals[0].level == "warn"
    assert signals[0].urgency == "normal"
    assert signals[0].dedup_key == "xsource|invoice|i-0001"
    assert signals[0].source_id == "i-0001"
    assert signals[0].source_ref == "i-0001"
    assert signals[0].due_at == date(2026, 6, 3)


def test_payment_required_signal_escalates_overdue_and_skips_acknowledged() -> None:
    supplier = Supplier(id="s-0017", name="Smith Heating")
    overdue = InvoiceRecord(
        id="i-0001",
        request_id="",
        supplier_id="s-0017",
        amount_minor=12500,
        invoice_date="2026-05-31",
        due_date="2026-05-31",
        description="Boiler repair",
        source="manual",
        status="emitted",
    )
    acknowledged = InvoiceRecord(
        id="i-0002",
        request_id="",
        supplier_id="s-0017",
        amount_minor=12500,
        invoice_date="2026-05-31",
        due_date="2026-06-03",
        description="Boiler repair",
        source="manual",
        status="acknowledged",
    )

    signals = build_payment_required_signals(
        [overdue, acknowledged], [supplier], today=_TODAY, now=_NOW
    )

    assert len(signals) == 1
    assert signals[0].source_id == "i-0001"
    assert signals[0].level == "error"
    assert signals[0].urgency == "high"


def test_invoice_variance_signal_uses_captured_invoice_state(tmp_path) -> None:
    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    requests = JsonlStore(tmp_path / "requests.jsonl", Request)
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    suppliers.upsert(
        Supplier(
            id="s-0017",
            name="Smith Heating",
            price_history=[
                {
                    "request_id": "r-0042",
                    "date": "2026-05-31",
                    "amount_minor": 10000,
                    "outcome": "used",
                }
            ],
        )
    )
    requests.upsert(
        Request(
            id="r-0042",
            created_at="2026-05-31T12:00:00+00:00",
            raw_need="boiler repair",
            chosen_supplier_id="s-0017",
        )
    )

    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="r-0042",
        supplier_id="s-0017",
        amount_minor=12000,
        invoice_number="INV-120",
        invoice_date="2026-06-01",
        due_date="2026-06-10",
        description="Boiler repair",
        source="manual",
        now="2026-06-01T07:00:00+00:00",
    )

    signals = build_invoice_variance_signals(
        invoices.all(), suppliers.all(), today=_TODAY, now=_NOW
    )

    assert report.variance is not None
    assert len(signals) == 1
    assert signals[0].kind == "action.required"
    assert signals[0].title == "Review invoice variance INV-120"
    assert "Smith Heating" in signals[0].detail
    assert "quoted GBP 100.00" in signals[0].detail
    assert "invoiced GBP 120.00" in signals[0].detail
    assert signals[0].dedup_key == f"xsource|invoice-variance|{report.invoice_id}"
    assert signals[0].source_id == report.invoice_id
    assert signals[0].due_at == _TODAY


def test_rejected_invoice_signal_is_operator_visible() -> None:
    supplier = Supplier(id="s-0017", name="Smith Heating")
    invoice = InvoiceRecord(
        id="i-0001",
        request_id="",
        supplier_id="s-0017",
        amount_minor=12500,
        invoice_date="2026-05-31",
        description="Boiler repair",
        source="manual",
        status="rejected",
        handoff={"rejection_reason": "missing VAT number"},
    )

    signals = build_rejected_invoice_signals([invoice], [supplier], today=_TODAY, now=_NOW)

    assert len(signals) == 1
    assert signals[0].kind == "action.required"
    assert signals[0].dedup_key == "xsource|invoice-rejected|i-0001"
    assert "missing VAT number" in signals[0].detail
    # The CTA must point at a real recovery path, not a dead capture-new walk.
    assert "invoice reemit i-0001" in signals[0].detail
    assert "invoice write-off i-0001" in signals[0].detail
