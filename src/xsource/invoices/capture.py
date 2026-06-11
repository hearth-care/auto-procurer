"""Invoice capture, linkage, and CSV import."""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xsource.store.models import InvoiceRecord


@dataclass(frozen=True)
class CaptureReport:
    invoice_id: str
    warnings: list[str]
    variance: dict[str, Any] | None = None
    operator_signal: dict[str, Any] | None = None


def _today_from_iso(value: str) -> str:
    return dt.datetime.fromisoformat(value).date().isoformat()


def _quote_minor(rows: list[dict[str, Any]], request_id: str) -> int | None:
    for row in reversed(rows):
        if row.get("request_id") != request_id:
            continue
        if row.get("outcome") not in {"used", "quoted"}:
            continue
        if isinstance(row.get("amount_minor"), int):
            return row["amount_minor"]
        if isinstance(row.get("amount"), int | float):
            return int(row["amount"] * 100)
    return None


def _variance(
    *,
    quoted_minor: int | None,
    invoiced_minor: int,
    tolerance: float,
) -> dict[str, Any] | None:
    if not quoted_minor:
        return None
    delta_ratio = round(abs(invoiced_minor - quoted_minor) / quoted_minor, 4)
    if delta_ratio <= tolerance:
        return None
    return {
        "quoted_minor": quoted_minor,
        "invoiced_minor": invoiced_minor,
        "delta_ratio": delta_ratio,
    }


def capture_invoice(
    *,
    suppliers,
    requests,
    invoices,
    request_id: str,
    supplier_id: str,
    amount_minor: int,
    invoice_number: str | None,
    invoice_date: str,
    due_date: str | None,
    description: str,
    source: str,
    now: str | None = None,
    currency: str = "GBP",
    file_ref: str | None = None,
    tolerance: float = 0.10,
) -> CaptureReport:
    now = now or dt.datetime.now(dt.UTC).isoformat()
    warnings: list[str] = []
    supplier = suppliers.get(supplier_id)
    if supplier is None:
        raise ValueError(f"unknown supplier id {supplier_id}")
    request = requests.get(request_id) if request_id else None
    if request_id and request is None:
        raise ValueError(f"unknown request id {request_id}")
    if request is not None and request.chosen_supplier_id and request.chosen_supplier_id != supplier_id:
        warnings.append(
            f"chosen supplier {request.chosen_supplier_id} differs from invoice supplier {supplier_id}"
        )

    quoted_minor = _quote_minor(supplier.price_history, request_id) if request_id else None
    variance = _variance(quoted_minor=quoted_minor, invoiced_minor=amount_minor, tolerance=tolerance)
    operator_signal = None
    if variance is not None:
        warnings.append(
            f"invoice amount {amount_minor} differs from quote {quoted_minor} by more than {tolerance:.0%}"
        )
        operator_signal = {
            "worker": "xsource",
            "kind": "action.required",
            "title": f"Review invoice variance {invoice_number or ''}".strip(),
            "source_id": "",
        }

    invoice = InvoiceRecord(
        id=invoices.next_id("i"),
        request_id=request_id,
        supplier_id=supplier_id,
        amount_minor=amount_minor,
        currency=currency,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        description=description,
        source=source,
        file_ref=file_ref,
        created_at=now,
        updated_at=now,
        handoff={"variance": variance} if variance is not None else {},
    )
    invoices.upsert(invoice)
    supplier.price_history.append(
        {
            "request_id": request_id,
            "date": _today_from_iso(now),
            "amount_minor": amount_minor,
            "outcome": "invoiced",
            "invoice_id": invoice.id,
        }
    )
    suppliers.upsert(supplier)
    if operator_signal is not None:
        operator_signal["source_id"] = invoice.id
    return CaptureReport(
        invoice_id=invoice.id,
        warnings=warnings,
        variance=variance,
        operator_signal=operator_signal,
    )


def _existing_invoice_keys(invoices) -> set[tuple[str, str]]:
    return {
        (invoice.supplier_id, invoice.invoice_number)
        for invoice in invoices.all()
        if invoice.invoice_number
    }


def import_csv(path: Path, *, suppliers, requests, invoices) -> dict[str, int]:
    existing = _existing_invoice_keys(invoices)
    imported = skipped = 0
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            supplier_id = (row.get("supplier_id") or "").strip()
            invoice_number = (row.get("invoice_number") or "").strip() or None
            if invoice_number and (supplier_id, invoice_number) in existing:
                skipped += 1
                continue
            capture_invoice(
                suppliers=suppliers,
                requests=requests,
                invoices=invoices,
                request_id=(row.get("request_id") or "").strip(),
                supplier_id=supplier_id,
                amount_minor=int((row.get("amount_minor") or "0").strip()),
                invoice_number=invoice_number,
                invoice_date=(row.get("invoice_date") or "").strip(),
                due_date=(row.get("due_date") or "").strip() or None,
                description=(row.get("description") or "").strip(),
                source="csv",
            )
            if invoice_number:
                existing.add((supplier_id, invoice_number))
            imported += 1
    return {"imported": imported, "skipped": skipped}
