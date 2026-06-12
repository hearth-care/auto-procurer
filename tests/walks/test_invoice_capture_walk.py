"""Tests for the invoice capture cockpit walk steps."""

from __future__ import annotations

from clonway_cockpit.walk import WizardContext
from rich.console import Console

from xsource.cli.cockpit import _invoice_apply_step, _invoice_details_step
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, Supplier


def _ctx(inputs: list[str]) -> WizardContext:
    it = iter(inputs)
    return WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda _prompt: next(it),
        confirm_fn=lambda _prompt: False,
    )


def test_invoice_details_step_rejects_non_numeric_amount():
    ctx = _ctx(["s-0001", "not-a-number", "2026-06-11", "Boiler repair"])
    result = _invoice_details_step(ctx, {})
    assert result.ok is False
    assert "not-a-number" in result.message


def test_invoice_details_step_rejects_zero_amount():
    ctx = _ctx(["s-0001", "0", "2026-06-11", "Boiler repair"])
    result = _invoice_details_step(ctx, {})
    assert result.ok is False
    assert "0" in result.message


def test_invoice_details_step_rejects_negative_amount():
    ctx = _ctx(["s-0001", "-500", "2026-06-11", "Boiler repair"])
    result = _invoice_details_step(ctx, {})
    assert result.ok is False
    assert "-500" in result.message


def test_invoice_details_step_accepts_valid_amount():
    ctx = _ctx(["s-0001", "12500", "2026-06-11", "Boiler repair", "", "", ""])
    result = _invoice_details_step(ctx, {})
    assert result.ok is True
    assert result.data["amount_minor"] == 12500
    assert result.data["supplier_id"] == "s-0001"


def test_invoice_details_step_rejects_malformed_invoice_date():
    ctx = _ctx(["s-0001", "12500", "11/06/2026", "Boiler repair", "", "", ""])
    result = _invoice_details_step(ctx, {})
    assert result.ok is False
    assert "invoice_date" in result.message


def test_invoice_details_step_rejects_malformed_due_date():
    ctx = _ctx(["s-0001", "12500", "2026-06-11", "Boiler repair", "", "", "30/06/2026"])
    result = _invoice_details_step(ctx, {})
    assert result.ok is False
    assert "due_date" in result.message


def test_invoice_apply_step_reports_invalid_date_without_raising(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    requests = JsonlStore(tmp_path / "requests.jsonl", Request)
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        cockpit_mod, "build_stores", lambda cfg: (suppliers, requests, invoices)
    )
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *args, **kwargs: True)

    result = _invoice_apply_step(
        _ctx([]),
        {
            "supplier_id": "s-0001",
            "amount_minor": 10000,
            "invoice_date": "11/06/2026",
            "description": "Bad date",
            "request_id": "",
            "invoice_number": "INV-BAD",
            "due_date": None,
        },
    )

    assert result.ok is False
    assert "invalid invoice_date" in result.message
    assert invoices.all() == []
