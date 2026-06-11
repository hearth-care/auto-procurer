"""Tests for the followup walk wiring: confirm/decline paths, operator identity."""

from __future__ import annotations

import datetime as dt

from clonway_cockpit.registry import WizardContext
from rich.console import Console

from xsource.cli.cockpit import _followup_apply_step, _followup_select_step
from xsource.p4.followup import create_followup_draft
from xsource.store.models import Request, ShortlistEntry, Supplier


def _ctx(*, confirm=True) -> WizardContext:
    return WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda *a, **k: "",
        confirm_fn=lambda _p: confirm,
        read_key=lambda: "a" if confirm else "\x1b",
    )


# ---------------------------------------------------------------------------
# _followup_select_step
# ---------------------------------------------------------------------------


def test_followup_select_step_requires_request_id():
    inputs = iter(["", "s-1"])
    ctx = WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda *a, **k: next(inputs),
        confirm_fn=lambda _p: False,
        read_key=lambda: "\x1b",
    )
    result = _followup_select_step(ctx, {})
    assert not result.ok


def test_followup_select_step_returns_ids():
    inputs = iter(["r-0042", "s-1"])
    ctx = WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda *a, **k: next(inputs),
        confirm_fn=lambda _p: False,
        read_key=lambda: "\x1b",
    )
    result = _followup_select_step(ctx, {})
    assert result.ok
    assert result.data["request_id"] == "r-0042"
    assert result.data["supplier_id"] == "s-1"


# ---------------------------------------------------------------------------
# _followup_apply_step — decline path (no Google credentials needed)
# ---------------------------------------------------------------------------


def test_followup_apply_step_decline_creates_no_draft():
    ctx = _ctx(confirm=False)
    result = _followup_apply_step(ctx, {"request_id": "r-0042", "supplier_id": "s-1"})
    assert not result.ok
    assert "declined" in result.message.lower()


# ---------------------------------------------------------------------------
# operator identity comes from parameter, not hardcoded
# ---------------------------------------------------------------------------


class _DraftClient:
    def __init__(self):
        self.calls: list = []

    def create_draft(self, *, to, subject, body, label):
        self.calls.append({"body": body})
        return {"draft_id": "fd-1", "message_id": "fm-1", "thread_id": "thr-1"}


def test_followup_draft_uses_operator_name_param():
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                reply={"summary": "Asked to visit before quoting."},
            )
        ],
    )
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")
    client = _DraftClient()

    create_followup_draft(
        request,
        supplier,
        draft_client=client,
        operator_name="Jane",
        now=dt.datetime(2026, 6, 11, 10, 0, tzinfo=dt.UTC),
    )

    assert "Jane" in client.calls[0]["body"]
    assert "Milo" not in client.calls[0]["body"]
