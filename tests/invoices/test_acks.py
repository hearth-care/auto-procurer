from __future__ import annotations

from pathlib import Path

from xsource.invoices.acks import ingest_ack_records
from xsource.invoices.capture import capture_invoice
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, Supplier


def _stores(tmp_path: Path):
    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    requests = JsonlStore(tmp_path / "requests.jsonl", Request)
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    return suppliers, requests, invoices


def _capture_one(tmp_path: Path) -> tuple:
    """Set up stores and capture a single invoice; return (suppliers, requests, invoices, invoice_id)."""
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    requests.upsert(
        Request(
            id="r-0001",
            created_at="2026-06-10T12:00:00+00:00",
            raw_need="boiler repair",
            chosen_supplier_id="s-0001",
        )
    )
    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="r-0001",
        supplier_id="s-0001",
        amount_minor=12500,
        invoice_number="INV-100",
        invoice_date="2026-06-11",
        due_date="2026-06-30",
        description="Boiler repair",
        source="manual",
        now="2026-06-11T12:00:00+00:00",
    )
    return suppliers, requests, invoices, report.invoice_id


def test_ingest_accepted_ack_from_captured_transitions_to_acknowledged(tmp_path):
    _, _, invoices, invoice_id = _capture_one(tmp_path)

    assert invoices.get(invoice_id).status == "captured"

    report = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": invoice_id,
                "consumer_run_id": "xbook-run-1",
                "disposition": "accepted",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )

    invoice = invoices.get(invoice_id)
    assert report == {"acknowledged": 1, "rejected": 0, "skipped": 0}
    assert invoice.status == "acknowledged"
    assert invoice.handoff["ack_ref"] == "xbook-run-1"
    assert invoice.updated_at == "2026-06-11T15:00:00+00:00"


def test_ingest_rejected_ack_from_captured_records_reason(tmp_path):
    _, _, invoices, invoice_id = _capture_one(tmp_path)

    assert invoices.get(invoice_id).status == "captured"

    report = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": invoice_id,
                "consumer_run_id": "xbook-run-2",
                "disposition": "rejected:missing VAT number",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )

    invoice = invoices.get(invoice_id)
    assert report == {"acknowledged": 0, "rejected": 1, "skipped": 0}
    assert invoice.status == "rejected"
    assert invoice.handoff["ack_ref"] == "xbook-run-2"
    assert invoice.handoff["rejection_reason"] == "missing VAT number"


def test_ingest_ack_also_works_from_emitted_state(tmp_path):
    """Re-emitted and emitted invoices should still be ack-able (regression guard)."""
    _, _, invoices, invoice_id = _capture_one(tmp_path)

    # Manually advance to emitted (simulates re-emit after a rejection cycle)
    invoice = invoices.get(invoice_id)
    invoice.transition_to("emitted")
    invoices.upsert(invoice)

    report = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": invoice_id,
                "consumer_run_id": "xbook-run-3",
                "disposition": "accepted",
                "timestamp": "2026-06-11T16:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )

    assert report == {"acknowledged": 1, "rejected": 0, "skipped": 0}
    assert invoices.get(invoice_id).status == "acknowledged"
