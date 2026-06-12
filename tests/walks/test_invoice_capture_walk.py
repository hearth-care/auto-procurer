"""Tests for the invoice capture cockpit walk steps."""

from __future__ import annotations

from clonway_cockpit.walk import WizardContext
from rich.console import Console

from xsource.cli.cockpit import _invoice_details_step


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
