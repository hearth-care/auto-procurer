"""Tests for the reorder capability, signal repoint, and dedup (S7/Phase 4)."""

from __future__ import annotations

from datetime import UTC, datetime

from xsource.signals.build import build_recurring_service_signals
from xsource.store.models import Request, Supplier

_NOW = datetime(2026, 6, 1, 7, 0, tzinfo=UTC)
_TODAY = _NOW.date()


# ---------------------------------------------------------------------------
# Signal repoint: capability_key changed from book.search → request.reorder
# ---------------------------------------------------------------------------


def test_recurring_signal_capability_key_is_request_reorder():
    supplier = Supplier(
        id="s-0017",
        name="Smith Heating",
        categories=["heating"],
        last_used="2025-06-15",
        recurs_every_months=12,
    )

    signals = build_recurring_service_signals([supplier], today=_TODAY, now=_NOW)

    assert len(signals) == 1
    assert signals[0].capability_key == "request.reorder"
    assert signals[0].focus == "s-0017"


# ---------------------------------------------------------------------------
# Dedup: supplier with an open reorder request → no signal
# ---------------------------------------------------------------------------


def test_recurring_signal_suppressed_when_open_reorder_request_exists():
    supplier = Supplier(
        id="s-0017",
        name="Smith Heating",
        categories=["heating"],
        last_used="2025-06-15",
        recurs_every_months=12,
    )
    open_reorder = Request(
        id="r-9001",
        created_at="2026-05-30T10:00:00",
        raw_need="Annual boiler service",
        status="open",
        constraints={"reorder_supplier_id": "s-0017"},
    )

    signals = build_recurring_service_signals([supplier], [open_reorder], today=_TODAY, now=_NOW)

    assert signals == ()


def test_recurring_signal_fires_when_reorder_request_is_closed():
    supplier = Supplier(
        id="s-0017",
        name="Smith Heating",
        categories=["heating"],
        last_used="2025-06-15",
        recurs_every_months=12,
    )
    closed_reorder = Request(
        id="r-9001",
        created_at="2026-05-30T10:00:00",
        raw_need="Annual boiler service",
        status="closed",
        constraints={"reorder_supplier_id": "s-0017"},
    )

    signals = build_recurring_service_signals([supplier], [closed_reorder], today=_TODAY, now=_NOW)

    assert len(signals) == 1


def test_recurring_signal_fires_when_different_supplier_has_open_reorder():
    supplier = Supplier(
        id="s-0017",
        name="Smith Heating",
        categories=["heating"],
        last_used="2025-06-15",
        recurs_every_months=12,
    )
    other_reorder = Request(
        id="r-9002",
        created_at="2026-05-30T10:00:00",
        raw_need="Some other service",
        status="open",
        constraints={"reorder_supplier_id": "s-9999"},
    )

    signals = build_recurring_service_signals([supplier], [other_reorder], today=_TODAY, now=_NOW)

    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Capability registration
# ---------------------------------------------------------------------------


def test_request_reorder_capability_is_registered():
    from clonway_cockpit import registry

    from xsource.cli import cockpit

    cockpit.register_all()
    keys = {spec.key for spec in registry.get_capabilities()}
    assert "request.reorder" in keys


def test_request_reorder_capability_has_run_handler():
    from clonway_cockpit import registry

    from xsource.cli import cockpit

    cockpit.register_all()
    specs = {spec.key: spec for spec in registry.get_capabilities()}
    assert specs["request.reorder"].run is not None


def test_request_trigger_capability_has_run_handler():
    from clonway_cockpit import registry

    from xsource.cli import cockpit

    cockpit.register_all()
    specs = {spec.key: spec for spec in registry.get_capabilities()}
    assert specs["request.trigger"].run is not None


def test_request_followup_capability_has_run_handler():
    from clonway_cockpit import registry

    from xsource.cli import cockpit

    cockpit.register_all()
    specs = {spec.key: spec for spec in registry.get_capabilities()}
    assert specs["request.followup"].run is not None


def test_partner_checkatrade_remains_build_only():
    from clonway_cockpit import registry

    from xsource.cli import cockpit

    cockpit.register_all()
    specs = {spec.key: spec for spec in registry.get_capabilities()}
    assert specs["partner.checkatrade"].run is None
    assert specs["partner.checkatrade"].equivalent_cli is None


# ---------------------------------------------------------------------------
# CLI commands registered
# ---------------------------------------------------------------------------


def test_new_cli_commands_are_registered():
    from typer.testing import CliRunner

    from xsource.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["request", "--help"])

    assert result.exit_code == 0
    assert "trigger" in result.stdout
    assert "followup" in result.stdout
    assert "reorder" in result.stdout
