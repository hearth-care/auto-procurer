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


def validate_iso_date(value: str, field: str) -> None:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"invalid {field} {value!r}: expected YYYY-MM-DD") from None


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
    validate_iso_date(invoice_date, "invoice_date")
    if due_date:
        validate_iso_date(due_date, "due_date")
    if amount_minor <= 0:
        raise ValueError(f"amount_minor must be a positive integer, got {amount_minor}")
    now = now or dt.datetime.now(dt.UTC).isoformat()
    warnings: list[str] = []
    supplier = suppliers.get(supplier_id)
    if supplier is None:
        raise ValueError(f"unknown supplier id {supplier_id}")
    request = requests.get(request_id) if request_id else None
    if request_id and request is None:
        raise ValueError(f"unknown request id {request_id}")
    if (
        request is not None
        and request.chosen_supplier_id
        and request.chosen_supplier_id != supplier_id
    ):
        warnings.append(
            f"chosen supplier {request.chosen_supplier_id} differs from invoice supplier {supplier_id}"
        )

    quoted_minor = _quote_minor(supplier.price_history, request_id) if request_id else None
    variance = _variance(
        quoted_minor=quoted_minor, invoiced_minor=amount_minor, tolerance=tolerance
    )
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


def reemit_invoice(
    invoices,
    invoice_id: str,
    *,
    suppliers=None,
    amount_minor: int | None = None,
    invoice_date: str | None = None,
    due_date: str | None = None,
    description: str | None = None,
    invoice_number: str | None = None,
    now: str | None = None,
) -> InvoiceRecord:
    """Correct a rejected invoice and return it to the emittable lifecycle.

    Only `rejected` invoices can be re-emitted (the consumer refused the handoff
    and the operator has fixed the underlying problem). Supplied fields overwrite
    the stored values; omitted fields are left unchanged. Validation matches
    capture so a re-emit can never push a malformed amount or date downstream.
    """
    invoice = invoices.get(invoice_id)
    if invoice is None:
        raise ValueError(f"unknown invoice id {invoice_id}")
    if invoice.status != "rejected":
        raise ValueError(
            f"invoice {invoice_id} is {invoice.status}; only rejected invoices can be re-emitted"
        )
    at = now or dt.datetime.now(dt.UTC).isoformat()
    if amount_minor is not None:
        if amount_minor <= 0:
            raise ValueError(f"amount_minor must be a positive integer, got {amount_minor}")
        if suppliers is None:
            raise ValueError("suppliers store is required when correcting amount_minor")
        invoice.amount_minor = amount_minor
    if invoice_date is not None:
        validate_iso_date(invoice_date, "invoice_date")
        invoice.invoice_date = invoice_date
    if due_date is not None:
        validate_iso_date(due_date, "due_date")
        invoice.due_date = due_date
    if description is not None:
        invoice.description = description
    if invoice_number is not None:
        invoice.invoice_number = invoice_number
    if amount_minor is not None:
        _refresh_amount_derivations(
            suppliers=suppliers,
            invoice=invoice,
            tolerance=0.10,
            at=at,
        )
    invoice.transition_to("emitted", at=at)
    invoice.handoff.pop("rejection_reason", None)
    invoices.upsert(invoice)
    return invoice


def _refresh_amount_derivations(
    *,
    suppliers,
    invoice: InvoiceRecord,
    tolerance: float,
    at: str,
) -> None:
    supplier = suppliers.get(invoice.supplier_id)
    if supplier is None:
        raise ValueError(f"unknown supplier id {invoice.supplier_id}")

    found_invoiced_row = False
    for row in supplier.price_history:
        if row.get("invoice_id") == invoice.id and row.get("outcome") == "invoiced":
            row["amount_minor"] = invoice.amount_minor
            found_invoiced_row = True
            break
    if not found_invoiced_row:
        supplier.price_history.append(
            {
                "request_id": invoice.request_id,
                "date": _today_from_iso(at),
                "amount_minor": invoice.amount_minor,
                "outcome": "invoiced",
                "invoice_id": invoice.id,
            }
        )

    quoted_minor = (
        _quote_minor(supplier.price_history, invoice.request_id) if invoice.request_id else None
    )
    variance = _variance(
        quoted_minor=quoted_minor,
        invoiced_minor=invoice.amount_minor,
        tolerance=tolerance,
    )
    if variance is None:
        if "variance" in invoice.handoff:
            invoice.handoff["variance_resolved_at"] = at
        invoice.handoff.pop("variance", None)
    else:
        invoice.handoff["variance"] = variance
        invoice.handoff.pop("variance_resolved_at", None)
    suppliers.upsert(supplier)


def write_off_invoice(invoices, invoice_id: str, *, now: str | None = None) -> InvoiceRecord:
    """Mark a rejected invoice written off when it will never be re-emitted."""
    invoice = invoices.get(invoice_id)
    if invoice is None:
        raise ValueError(f"unknown invoice id {invoice_id}")
    if invoice.status != "rejected":
        raise ValueError(
            f"invoice {invoice_id} is {invoice.status}; only rejected invoices can be written off"
        )
    invoice.transition_to("written_off", at=now)
    invoices.upsert(invoice)
    return invoice


def _existing_invoice_keys(invoices) -> set[tuple[str, str]]:
    return {
        (invoice.supplier_id, invoice.invoice_number)
        for invoice in invoices.all()
        if invoice.invoice_number
    }


def import_csv(path: Path, *, suppliers, requests, invoices) -> dict[str, int]:
    existing = _existing_invoice_keys(invoices)
    imported = skipped = errored = 0
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            supplier_id = (row.get("supplier_id") or "").strip()
            invoice_number = (row.get("invoice_number") or "").strip() or None
            if not invoice_number:
                errored += 1
                continue
            if (supplier_id, invoice_number) in existing:
                skipped += 1
                continue
            raw_amount = (row.get("amount_minor") or "").strip()
            try:
                amount_minor = int(raw_amount)
            except (ValueError, TypeError):
                errored += 1
                continue
            if amount_minor <= 0:
                errored += 1
                continue
            try:
                capture_invoice(
                    suppliers=suppliers,
                    requests=requests,
                    invoices=invoices,
                    request_id=(row.get("request_id") or "").strip(),
                    supplier_id=supplier_id,
                    amount_minor=amount_minor,
                    invoice_number=invoice_number,
                    invoice_date=(row.get("invoice_date") or "").strip(),
                    due_date=(row.get("due_date") or "").strip() or None,
                    description=(row.get("description") or "").strip(),
                    source="csv",
                )
            except ValueError:
                errored += 1
                continue
            existing.add((supplier_id, invoice_number))
            imported += 1
    return {"imported": imported, "skipped": skipped, "errored": errored}
