from __future__ import annotations

from xsource.invoices.acks import ingest_ack_records
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord


def test_ingest_accepted_ack_transitions_invoice_to_acknowledged(tmp_path):
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    invoices.upsert(
        InvoiceRecord(
            id="i-0001",
            request_id="",
            supplier_id="s-0001",
            amount_minor=12500,
            invoice_date="2026-06-11",
            description="Boiler repair",
            source="manual",
            status="emitted",
        )
    )

    report = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": "i-0001",
                "consumer_run_id": "xbook-run-1",
                "disposition": "accepted",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )

    invoice = invoices.get("i-0001")
    assert report == {"acknowledged": 1, "rejected": 0, "skipped": 0}
    assert invoice.status == "acknowledged"
    assert invoice.handoff["ack_ref"] == "xbook-run-1"
    assert invoice.updated_at == "2026-06-11T15:00:00+00:00"


def test_ingest_rejected_ack_records_reason(tmp_path):
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    invoices.upsert(
        InvoiceRecord(
            id="i-0001",
            request_id="",
            supplier_id="s-0001",
            amount_minor=12500,
            invoice_date="2026-06-11",
            description="Boiler repair",
            source="manual",
            status="emitted",
        )
    )

    report = ingest_ack_records(
        invoices,
        [
            {
                "invoice_id": "i-0001",
                "consumer_run_id": "xbook-run-2",
                "disposition": "rejected:missing VAT number",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "contract_version": 1,
            }
        ],
    )

    invoice = invoices.get("i-0001")
    assert report == {"acknowledged": 0, "rejected": 1, "skipped": 0}
    assert invoice.status == "rejected"
    assert invoice.handoff["ack_ref"] == "xbook-run-2"
    assert invoice.handoff["rejection_reason"] == "missing VAT number"
