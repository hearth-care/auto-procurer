"""Unit tests for the reorder proposal engine (S7/Phase 3)."""

from __future__ import annotations

from xsource.p4.reorder import build_reorder_proposal
from xsource.store.models import Request, Supplier


def _supplier(**kwargs) -> Supplier:
    defaults = dict(
        id="s-0017",
        name="Smith Heating",
        categories=["heating"],
        last_used="2025-06-15",
        recurs_every_months=12,
    )
    defaults.update(kwargs)
    return Supplier(**defaults)


def _request(rid: str, raw_need: str) -> Request:
    return Request(id=rid, created_at="2025-06-15T10:00:00", raw_need=raw_need)


# ---------------------------------------------------------------------------
# raw_need derivation
# ---------------------------------------------------------------------------


def test_raw_need_comes_from_most_recent_used_request():
    supplier = _supplier(
        price_history=[
            {"outcome": "used", "request_id": "r-001", "date": "2025-06-15", "amount": 180},
        ]
    )
    requests = [_request("r-001", "Annual boiler service")]

    proposal = build_reorder_proposal(supplier, requests)

    assert proposal.raw_need == "Annual boiler service"


def test_raw_need_falls_back_to_category_when_no_used_request():
    supplier = _supplier(categories=["plumbing"], price_history=[])

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.raw_need == "plumbing"


def test_raw_need_falls_back_to_supplier_name_when_no_category():
    supplier = _supplier(categories=[], price_history=[])

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.raw_need == "general"


def test_most_recent_request_wins_when_multiple_used_entries():
    supplier = _supplier(
        price_history=[
            {"outcome": "used", "request_id": "r-001", "date": "2024-06-01", "amount": 160},
            {"outcome": "used", "request_id": "r-002", "date": "2025-06-15", "amount": 180},
        ]
    )
    requests = [
        _request("r-001", "Older boiler service"),
        _request("r-002", "Recent boiler service"),
    ]

    proposal = build_reorder_proposal(supplier, requests)

    assert proposal.raw_need == "Recent boiler service"


# ---------------------------------------------------------------------------
# Rank-1 pinning (preferred supplier)
# ---------------------------------------------------------------------------


def test_proposal_has_correct_supplier_id():
    supplier = _supplier(id="s-0017", preferred=True)

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.supplier_id == "s-0017"
    assert proposal.supplier_name == "Smith Heating"


# ---------------------------------------------------------------------------
# Budget hint
# ---------------------------------------------------------------------------


def test_budget_hint_median_from_used_entries():
    supplier = _supplier(
        price_history=[
            {"outcome": "used", "amount": 160, "date": "2023-06-01"},
            {"outcome": "used", "amount": 180, "date": "2024-06-01"},
            {"outcome": "used", "amount": 200, "date": "2025-06-15"},
        ]
    )

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.budget_hint["median"] == 180
    assert proposal.budget_hint["low"] == 160
    assert proposal.budget_hint["high"] == 200
    assert proposal.budget_hint["sample_size"] == 3


def test_budget_hint_empty_when_no_used_entries():
    supplier = _supplier(price_history=[])

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.budget_hint["median"] is None
    assert proposal.budget_hint["sample_size"] == 0


def test_budget_hint_ignores_quoted_not_used_entries():
    supplier = _supplier(
        price_history=[
            {"outcome": "quoted", "amount": 999, "date": "2025-06-01"},
            {"outcome": "used", "amount": 180, "date": "2025-06-15"},
        ]
    )

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.budget_hint["median"] == 180
    assert proposal.budget_hint["sample_size"] == 1


# ---------------------------------------------------------------------------
# Cadence context
# ---------------------------------------------------------------------------


def test_proposal_records_last_done_and_due_at():
    supplier = _supplier(last_used="2025-06-15", recurs_every_months=12)

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.last_done == "2025-06-15"
    assert proposal.due_at == "2026-06-15"
    assert proposal.cadence_months == 12


def test_due_at_empty_when_missing_recurrence_info():
    supplier = _supplier(last_used=None, recurs_every_months=None)

    proposal = build_reorder_proposal(supplier, [])

    assert proposal.due_at == ""
