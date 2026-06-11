"""Build a prefilled reorder proposal for a recurring supplier."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from xsource.store.models import Request, Supplier


@dataclass(frozen=True)
class ReorderProposal:
    supplier_id: str
    supplier_name: str
    raw_need: str
    category: str
    budget_hint: dict[str, Any]
    last_done: str | None
    due_at: str
    cadence_months: int


def build_reorder_proposal(
    supplier: Supplier,
    requests: Sequence[Request],
) -> ReorderProposal:
    """Build a prefilled reorder proposal.

    raw_need: from the most recent "used" request, falling back to the supplier's
    primary category name.
    budget_hint: median/low/high from used price_history entries (sample_size labelled).
    """
    used_entries = [e for e in supplier.price_history if e.get("outcome") == "used"]
    sorted_used = sorted(used_entries, key=lambda e: str(e.get("date", "")), reverse=True)

    request_by_id = {r.id: r for r in requests}
    raw_need: str | None = None
    for entry in sorted_used:
        rid = entry.get("request_id")
        if rid and rid in request_by_id:
            raw_need = request_by_id[rid].raw_need
            break

    category = supplier.categories[0] if supplier.categories else "general"
    if raw_need is None:
        raw_need = category

    amounts = [int(e["amount"]) for e in sorted_used if e.get("amount") is not None]
    if amounts:
        budget_hint: dict[str, Any] = {
            "median": int(statistics.median(amounts)),
            "low": min(amounts),
            "high": max(amounts),
            "sample_size": len(amounts),
        }
    else:
        budget_hint = {"median": None, "low": None, "high": None, "sample_size": 0}

    return ReorderProposal(
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        raw_need=raw_need,
        category=category,
        budget_hint=budget_hint,
        last_done=supplier.last_used,
        due_at=_due_at(supplier),
        cadence_months=supplier.recurs_every_months or 0,
    )


def _due_at(supplier: Supplier) -> str:
    from xsource.signals.build import _add_months, _parse_date

    if supplier.last_used and supplier.recurs_every_months:
        last = _parse_date(supplier.last_used)
        if last:
            return _add_months(last, supplier.recurs_every_months).isoformat()
    return ""
