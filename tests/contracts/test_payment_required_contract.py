from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from xsource.invoices.acks import ingest_ack_records, read_ack_jsonl
from xsource.signals.build import build_payment_required_signals
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Supplier

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "contracts" / "fixtures"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_payment_required_contract_doc_exists():
    doc = ROOT / "docs" / "contracts" / "payment-required-v1.md"

    text = doc.read_text()

    assert "contract_version: 1" in text
    assert "payment.required" in text
    assert "dedup_key" in text
    assert "payment-required-acks.jsonl" in text


def test_payment_required_latest_fixture_matches_emitter():
    invoice = InvoiceRecord(
        id="i-0001",
        request_id="r-0001",
        supplier_id="s-0001",
        amount_minor=12500,
        currency="GBP",
        invoice_number="INV-100",
        invoice_date="2026-06-01",
        due_date="2026-06-03",
        description="Boiler repair",
        source="manual",
        status="captured",
    )
    supplier = Supplier(id="s-0001", name="Smith Heating")

    signals = build_payment_required_signals(
        [invoice],
        [supplier],
        today=date(2026, 6, 1),
        now=datetime(2026, 6, 1, 7, 0, tzinfo=UTC),
    )

    assert [signal.to_wire() for signal in signals] == _jsonl(FIXTURES / "latest.jsonl")


def test_payment_required_ack_fixture_is_ingestable(tmp_path):
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    invoices.upsert(
        InvoiceRecord(
            id="i-0001",
            request_id="r-0001",
            supplier_id="s-0001",
            amount_minor=12500,
            invoice_number="INV-100",
            invoice_date="2026-06-01",
            due_date="2026-06-03",
            description="Boiler repair",
            source="manual",
            status="emitted",
        )
    )

    report = ingest_ack_records(invoices, read_ack_jsonl(FIXTURES / "acks.jsonl"))

    assert report == {"acknowledged": 1, "rejected": 0, "skipped": 0}
    assert invoices.get("i-0001").status == "acknowledged"
