"""Operator recovery path for rejected invoices: edit + re-emit, or write off."""

from __future__ import annotations

from pathlib import Path

import pytest

from xsource.invoices.acks import ingest_ack_records
from xsource.invoices.capture import capture_invoice, reemit_invoice, write_off_invoice
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, Supplier


def _stores(tmp_path: Path):
    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    requests = JsonlStore(tmp_path / "requests.jsonl", Request)
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    return suppliers, requests, invoices


def _rejected_invoice(tmp_path: Path) -> tuple:
    """Capture an invoice and drive it to a rejected state via a real ack record."""
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="",
        supplier_id="s-0001",
        amount_minor=12500,
        invoice_number="INV-100",
        invoice_date="2026-06-11",
        due_date="2026-06-30",
        description="Boiler repair",
        source="manual",
        now="2026-06-11T12:00:00+00:00",
    )
    invoice_id = report.invoice_id
    ack = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": invoice_id,
                "consumer_run_id": "xbook-run-1",
                "disposition": "rejected:missing VAT number",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )
    assert ack == {"acknowledged": 0, "rejected": 1, "skipped": 0}
    assert invoices.get(invoice_id).status == "rejected"
    return suppliers, requests, invoices, invoice_id


def test_reemit_corrects_and_returns_invoice_to_emittable(tmp_path):
    _, _, invoices, invoice_id = _rejected_invoice(tmp_path)

    invoice = reemit_invoice(
        invoices,
        invoice_id,
        amount_minor=13000,
        description="Boiler repair (corrected VAT)",
        now="2026-06-11T17:00:00+00:00",
    )

    assert invoice.status == "emitted"
    assert invoice.amount_minor == 13000
    assert invoice.description == "Boiler repair (corrected VAT)"
    assert "rejection_reason" not in invoice.handoff
    assert invoices.get(invoice_id).status == "emitted"
    assert invoices.get(invoice_id).updated_at == "2026-06-11T17:00:00+00:00"


def test_reemitted_invoice_can_be_acknowledged_end_to_end(tmp_path):
    _, _, invoices, invoice_id = _rejected_invoice(tmp_path)
    reemit_invoice(invoices, invoice_id, now="2026-06-11T17:00:00+00:00")

    report = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": invoice_id,
                "consumer_run_id": "xbook-run-2",
                "disposition": "accepted",
                "timestamp": "2026-06-11T18:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )

    assert report == {"acknowledged": 1, "rejected": 0, "skipped": 0}
    assert invoices.get(invoice_id).status == "acknowledged"


def test_reemit_rejects_non_positive_amount(tmp_path):
    _, _, invoices, invoice_id = _rejected_invoice(tmp_path)
    with pytest.raises(ValueError):
        reemit_invoice(invoices, invoice_id, amount_minor=0)
    assert invoices.get(invoice_id).status == "rejected"


def test_reemit_rejects_malformed_due_date(tmp_path):
    _, _, invoices, invoice_id = _rejected_invoice(tmp_path)
    with pytest.raises(ValueError):
        reemit_invoice(invoices, invoice_id, due_date="30/06/2026")
    assert invoices.get(invoice_id).status == "rejected"


def test_reemit_only_from_rejected(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="",
        supplier_id="s-0001",
        amount_minor=12500,
        invoice_number="INV-200",
        invoice_date="2026-06-11",
        due_date=None,
        description="Captured only",
        source="manual",
        now="2026-06-11T12:00:00+00:00",
    )
    with pytest.raises(ValueError):
        reemit_invoice(invoices, report.invoice_id)


def test_reemit_unknown_invoice_raises(tmp_path):
    _, _, invoices = _stores(tmp_path)
    with pytest.raises(ValueError):
        reemit_invoice(invoices, "i-9999")


def test_write_off_rejected_invoice(tmp_path):
    _, _, invoices, invoice_id = _rejected_invoice(tmp_path)

    invoice = write_off_invoice(invoices, invoice_id, now="2026-06-11T19:00:00+00:00")

    assert invoice.status == "written_off"
    assert invoices.get(invoice_id).status == "written_off"
    assert invoices.get(invoice_id).updated_at == "2026-06-11T19:00:00+00:00"


def test_write_off_only_from_rejected(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="",
        supplier_id="s-0001",
        amount_minor=12500,
        invoice_number="INV-300",
        invoice_date="2026-06-11",
        due_date=None,
        description="Captured only",
        source="manual",
        now="2026-06-11T12:00:00+00:00",
    )
    with pytest.raises(ValueError):
        write_off_invoice(invoices, report.invoice_id)
