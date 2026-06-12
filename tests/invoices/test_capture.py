from __future__ import annotations

from pathlib import Path

from xsource.invoices.capture import capture_invoice, import_csv
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, Supplier


def _stores(tmp_path: Path):
    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    requests = JsonlStore(tmp_path / "requests.jsonl", Request)
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    return suppliers, requests, invoices


def test_capture_links_invoice_to_supplier_request_and_price_history(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(
        Supplier(
            id="s-0001",
            name="Smith Heating",
            price_history=[
                {
                    "request_id": "r-0001",
                    "date": "2026-06-10",
                    "amount_minor": 12000,
                    "outcome": "used",
                }
            ],
        )
    )
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
        amount_minor=12600,
        invoice_number="INV-100",
        invoice_date="2026-06-11",
        due_date="2026-06-30",
        description="Boiler repair",
        source="manual",
        now="2026-06-11T14:00:00+00:00",
    )

    invoice = invoices.get(report.invoice_id)
    supplier = suppliers.get("s-0001")
    assert invoice is not None
    assert invoice.request_id == "r-0001"
    assert invoice.status == "captured"
    assert supplier.price_history[-1] == {
        "request_id": "r-0001",
        "date": "2026-06-11",
        "amount_minor": 12600,
        "outcome": "invoiced",
        "invoice_id": invoice.id,
    }
    assert report.warnings == []
    assert report.variance is None


def test_capture_warns_on_chosen_supplier_mismatch(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Chosen Co"))
    suppliers.upsert(Supplier(id="s-0002", name="Invoice Co"))
    requests.upsert(
        Request(
            id="r-0001",
            created_at="2026-06-10T12:00:00+00:00",
            raw_need="repair",
            chosen_supplier_id="s-0001",
        )
    )

    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="r-0001",
        supplier_id="s-0002",
        amount_minor=10000,
        invoice_number="INV-101",
        invoice_date="2026-06-11",
        due_date=None,
        description="Repair",
        source="manual",
        now="2026-06-11T14:00:00+00:00",
    )

    assert "chosen supplier s-0001 differs from invoice supplier s-0002" in report.warnings


def test_capture_flags_variance_above_tolerance_boundary(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(
        Supplier(
            id="s-0001",
            name="Smith Heating",
            price_history=[
                {
                    "request_id": "r-0001",
                    "date": "2026-06-10",
                    "amount_minor": 10000,
                    "outcome": "used",
                }
            ],
        )
    )
    requests.upsert(
        Request(
            id="r-0001",
            created_at="2026-06-10T12:00:00+00:00",
            raw_need="repair",
            chosen_supplier_id="s-0001",
        )
    )

    at_boundary = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="r-0001",
        supplier_id="s-0001",
        amount_minor=11000,
        invoice_number="INV-102",
        invoice_date="2026-06-11",
        due_date=None,
        description="Repair",
        source="manual",
        now="2026-06-11T14:00:00+00:00",
    )
    above_boundary = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id="r-0001",
        supplier_id="s-0001",
        amount_minor=11001,
        invoice_number="INV-103",
        invoice_date="2026-06-11",
        due_date=None,
        description="Repair",
        source="manual",
        now="2026-06-11T14:05:00+00:00",
    )

    assert at_boundary.variance is None
    assert above_boundary.variance == {
        "quoted_minor": 10000,
        "invoiced_minor": 11001,
        "delta_ratio": 0.1001,
    }
    assert above_boundary.operator_signal is not None
    assert above_boundary.operator_signal["kind"] == "action.required"


def test_import_csv_is_idempotent_on_supplier_and_invoice_number(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    csv_path = tmp_path / "invoices.csv"
    csv_path.write_text(
        "supplier_id,invoice_number,amount_minor,invoice_date,due_date,description,request_id\n"
        "s-0001,INV-100,12500,2026-06-11,2026-06-30,Boiler repair,\n"
    )

    first = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)
    second = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)

    assert first == {"imported": 1, "skipped": 0, "errored": 0}
    assert second == {"imported": 0, "skipped": 1, "errored": 0}
    assert len(invoices.all()) == 1


def test_capture_rejects_malformed_invoice_date(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))

    import pytest

    with pytest.raises(ValueError, match="invoice_date"):
        capture_invoice(
            suppliers=suppliers,
            requests=requests,
            invoices=invoices,
            request_id="",
            supplier_id="s-0001",
            amount_minor=10000,
            invoice_number="INV-BAD",
            invoice_date="11/06/2026",
            due_date=None,
            description="Bad date",
            source="manual",
        )

    assert len(invoices.all()) == 0


def test_capture_rejects_malformed_due_date(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))

    import pytest

    with pytest.raises(ValueError, match="due_date"):
        capture_invoice(
            suppliers=suppliers,
            requests=requests,
            invoices=invoices,
            request_id="",
            supplier_id="s-0001",
            amount_minor=10000,
            invoice_number="INV-BAD2",
            invoice_date="2026-06-11",
            due_date="30/06/2026",
            description="Bad due date",
            source="manual",
        )

    assert len(invoices.all()) == 0


def test_import_csv_missing_amount_does_not_persist_invoice(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    csv_path = tmp_path / "invoices.csv"
    csv_path.write_text(
        "supplier_id,invoice_number,invoice_date,due_date,description,request_id\n"
        "s-0001,INV-MISSING,2026-06-11,2026-06-30,No amount column,\n"
    )

    result = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)

    assert result == {"imported": 0, "skipped": 0, "errored": 1}
    assert len(invoices.all()) == 0


def test_import_csv_zero_amount_does_not_persist_invoice(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    csv_path = tmp_path / "invoices.csv"
    csv_path.write_text(
        "supplier_id,invoice_number,amount_minor,invoice_date,due_date,description,request_id\n"
        "s-0001,INV-ZERO,0,2026-06-11,2026-06-30,Zero amount,\n"
    )

    result = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)

    assert result == {"imported": 0, "skipped": 0, "errored": 1}
    assert len(invoices.all()) == 0


def test_capture_rejects_zero_amount(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))

    import pytest

    with pytest.raises(ValueError, match="amount_minor"):
        capture_invoice(
            suppliers=suppliers,
            requests=requests,
            invoices=invoices,
            request_id="",
            supplier_id="s-0001",
            amount_minor=0,
            invoice_number="INV-ZERO",
            invoice_date="2026-06-11",
            due_date=None,
            description="Zero amount",
            source="manual",
        )

    assert len(invoices.all()) == 0


def test_capture_rejects_negative_amount(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))

    import pytest

    with pytest.raises(ValueError, match="amount_minor"):
        capture_invoice(
            suppliers=suppliers,
            requests=requests,
            invoices=invoices,
            request_id="",
            supplier_id="s-0001",
            amount_minor=-1000,
            invoice_number="INV-NEG",
            invoice_date="2026-06-11",
            due_date=None,
            description="Negative amount",
            source="manual",
        )

    assert len(invoices.all()) == 0


def test_import_csv_blank_invoice_number_does_not_persist_invoice(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    csv_path = tmp_path / "invoices.csv"
    csv_path.write_text(
        "supplier_id,invoice_number,amount_minor,invoice_date,due_date,description,request_id\n"
        "s-0001,,12500,2026-06-11,2026-06-30,No invoice number,\n"
    )

    first = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)
    second = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)

    assert first == {"imported": 0, "skipped": 0, "errored": 1}
    assert second == {"imported": 0, "skipped": 0, "errored": 1}
    assert len(invoices.all()) == 0


def test_import_csv_malformed_date_does_not_persist_invoice(tmp_path):
    suppliers, requests, invoices = _stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    csv_path = tmp_path / "invoices.csv"
    csv_path.write_text(
        "supplier_id,invoice_number,amount_minor,invoice_date,due_date,description,request_id\n"
        "s-0001,INV-BADDATE,10000,11/06/2026,2026-06-30,UK format date,\n"
    )

    result = import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices)

    assert result == {"imported": 0, "skipped": 0, "errored": 1}
    assert len(invoices.all()) == 0
