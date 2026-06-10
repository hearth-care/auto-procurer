"""Apply human-edited Sheet rows back into the xsource store."""

from __future__ import annotations

import datetime as dt
from typing import Any

from xsource.store.models import Request


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "yes", "y", "true", "chosen", "✓", "x"}


def _amount(value: Any) -> int | None:
    text = str(value or "").strip().replace("£", "").replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def apply_sheet_rows(
    request: Request,
    rows: list[dict[str, Any]],
    *,
    suppliers,
    synced_at: dt.datetime,
) -> dict[str, list[str] | int]:
    warnings: list[str] = []
    updated_suppliers = 0
    entry_by_rank = {entry.rank: entry for entry in request.shortlist}
    today = synced_at.date().isoformat()

    for row in rows:
        rank = int(row.get("rank") or 0)
        entry = entry_by_rank.get(rank)
        if entry is None:
            warnings.append(f"unknown rank {rank}")
            continue
        supplier = suppliers.get(entry.supplier_id)
        if supplier is None:
            warnings.append(f"unknown supplier {entry.supplier_id}")
            continue

        quote = _amount(row.get("quote"))
        status = str(row.get("status") or "").strip()
        notes = str(row.get("notes") or "").strip()
        chosen = _truthy(row.get("chosen")) or status.lower() == "chosen"

        if quote is not None:
            supplier.price_history.append(
                {
                    "request_id": request.id,
                    "date": today,
                    "amount": quote,
                    "outcome": "used" if chosen else "quoted",
                }
            )
            entry.reply["quote_amount"] = quote
        if notes:
            supplier.notes.append({"date": today, "request_id": request.id, "text": notes})
        if status:
            entry.reply["status"] = status.lower()
        if chosen:
            request.status = "closed"
            request.chosen_supplier_id = supplier.id
            supplier.last_used = today
        suppliers.upsert(supplier)
        updated_suppliers += 1

    request.watcher["last_sheet_sync_at"] = synced_at.isoformat()
    return {"updated_suppliers": updated_suppliers, "warnings": warnings}
