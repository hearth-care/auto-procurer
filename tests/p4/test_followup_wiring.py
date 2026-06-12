"""Tests for the followup walk wiring: confirm/decline paths, operator identity."""

from __future__ import annotations

import datetime as dt
import io

from clonway_cockpit.registry import WizardContext
from rich.console import Console
from typer.testing import CliRunner

from xsource.cli import app
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


def _request_with_replies() -> Request:
    return Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                reply={"summary": "Asked to visit before quoting."},
            ),
            ShortlistEntry(supplier_id="s-2", rank=2),
        ],
    )


class _FakeRequests:
    offline = False

    def __init__(self, request: Request):
        self.request = request
        self.upserted: list[Request] = []

    def get(self, id_):
        return self.request if id_ == self.request.id else None

    def all(self):
        return [self.request]

    def upsert(self, request):
        self.upserted.append(request)


class _FakeSuppliers:
    offline = False

    def __init__(self, suppliers: list[Supplier]):
        self.suppliers = suppliers

    def all(self):
        return self.suppliers


class _FakeCfg:
    operator_display_name = "Jane"


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


def test_followup_select_step_returns_ids(monkeypatch):
    from xsource.cli import cockpit as cmod

    request = _request_with_replies()
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")
    monkeypatch.setattr(
        cmod,
        "build_stores",
        lambda cfg: (_FakeSuppliers([supplier]), _FakeRequests(request), _FakeRequests(request)),
    )
    monkeypatch.setattr(cmod.Config, "from_env", classmethod(lambda cls: _FakeCfg()))

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


def test_followup_select_step_uses_focus_prefill(monkeypatch):
    """When focus="request.followup:{req}:{sup}" is set, no interactive input is needed."""
    from xsource.cli import cockpit as cmod

    request = _request_with_replies()
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")
    monkeypatch.setattr(
        cmod,
        "build_stores",
        lambda cfg: (_FakeSuppliers([supplier]), _FakeRequests(request), _FakeRequests(request)),
    )
    monkeypatch.setattr(cmod.Config, "from_env", classmethod(lambda cls: _FakeCfg()))

    ctx = WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("input_fn must not be called when focus pre-fills IDs")
        ),
        confirm_fn=lambda _p: False,
        read_key=lambda: "\x1b",
        focus="request.followup:r-0042:s-1",
    )
    result = _followup_select_step(ctx, {})
    assert result.ok, result.message
    assert result.data["request_id"] == "r-0042"
    assert result.data["supplier_id"] == "s-1"


def test_followup_select_step_lists_replied_suppliers_and_previews_body(monkeypatch):
    from xsource.cli import cockpit as cmod

    request = _request_with_replies()
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")
    monkeypatch.setattr(
        cmod,
        "build_stores",
        lambda cfg: (
            _FakeSuppliers([supplier, Supplier(id="s-2", name="No Reply Co")]),
            _FakeRequests(request),
            _FakeRequests(request),
        ),
    )
    monkeypatch.setattr(cmod.Config, "from_env", classmethod(lambda cls: _FakeCfg()))

    inputs = iter(["r-0042", "s-1"])
    output = io.StringIO()
    ctx = WizardContext(
        state={},
        client=None,
        console=Console(file=output, force_terminal=False, color_system=None),
        input_fn=lambda *a, **k: next(inputs),
        confirm_fn=lambda _p: False,
        read_key=lambda: "\x1b",
    )

    result = _followup_select_step(ctx, {})

    assert result.ok, result.message
    assert result.data["request"] is request
    assert result.data["supplier"] is supplier
    assert "Asked to visit before quoting." in output.getvalue()
    assert "Thanks for getting back to us about tree chipping" in output.getvalue()


# ---------------------------------------------------------------------------
# _followup_apply_step — decline path (no Google credentials needed)
# ---------------------------------------------------------------------------


def test_followup_apply_step_decline_creates_no_draft():
    ctx = _ctx(confirm=False)
    result = _followup_apply_step(ctx, {"request_id": "r-0042", "supplier_id": "s-1"})
    assert not result.ok
    assert "declined" in result.message.lower()


def test_followup_cli_opens_cockpit_with_focus(monkeypatch):
    """CLI validates inputs then hands off to run_cockpit — never creates a draft directly."""
    import xsource.cli.cockpit as cockpit_mod
    import xsource.p4.followup as followup_mod
    from xsource.cli import request as request_mod

    request = _request_with_replies()
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")
    cockpit_calls: list[str] = []
    draft_calls: list[dict] = []

    monkeypatch.setattr(
        request_mod,
        "build_stores",
        lambda cfg: (_FakeSuppliers([supplier]), _FakeRequests(request), _FakeRequests(request)),
    )
    monkeypatch.setattr(request_mod.Config, "from_env", classmethod(lambda cls: _FakeCfg()))
    monkeypatch.setattr(
        followup_mod,
        "create_followup_draft",
        lambda *a, **k: draft_calls.append({}) or {"draft_id": "fd-1"},
    )
    monkeypatch.setattr(
        cockpit_mod,
        "run_cockpit",
        lambda **kw: cockpit_calls.append(kw.get("focus", "")),
    )

    result = CliRunner().invoke(app, ["request", "followup", "r-0042", "s-1"])

    assert result.exit_code == 0, result.output
    assert draft_calls == [], "CLI must not create drafts directly"
    assert cockpit_calls == ["request.followup:r-0042:s-1"]


def test_followup_cli_rejects_missing_reply(monkeypatch):
    """CLI raises BadParameter when supplier has no recorded reply."""
    from xsource.cli import request as request_mod

    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],  # no reply
    )
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")

    monkeypatch.setattr(
        request_mod,
        "build_stores",
        lambda cfg: (_FakeSuppliers([supplier]), _FakeRequests(request), _FakeRequests(request)),
    )
    monkeypatch.setattr(request_mod.Config, "from_env", classmethod(lambda cls: _FakeCfg()))

    result = CliRunner().invoke(app, ["request", "followup", "r-0042", "s-1"])

    assert result.exit_code != 0


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


# ---------------------------------------------------------------------------
# followup metadata must be persisted to the store after draft creation
# ---------------------------------------------------------------------------


def test_followup_apply_step_persists_metadata_via_upsert(monkeypatch):
    """After a successful draft, followup_* fields must be written to the store (upsert)."""

    from xsource.cli import cockpit as cmod

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

    upserted: list = []

    class _FakeRequests:
        offline = False

        def get(self, id_):
            return request

        def all(self):
            return [request]

        def upsert(self, r):
            upserted.append(r)

    class _FakeSuppliers:
        offline = False

        def all(self):
            return [supplier]

    class _FakeCfg:
        operator_display_name = "Jane"

    class _FakeDraftClient:
        def create_draft(self, *, to, subject, body, label):
            return {"draft_id": "fd-1", "message_id": "fm-1", "thread_id": "thr-1"}

    class _FakeService:
        pass

    monkeypatch.setattr(
        cmod, "build_stores", lambda cfg: (_FakeSuppliers(), _FakeRequests(), _FakeRequests())
    )
    monkeypatch.setattr(cmod.Config, "from_env", classmethod(lambda cls: _FakeCfg()))
    monkeypatch.setenv("XSOURCE_GMAIL_TOKEN_PATH", "/nonexistent")

    import xsource.outreach.client as out_mod

    monkeypatch.setattr(out_mod, "SafeOutreachClient", lambda svc: _FakeDraftClient())

    import importlib

    google_oauth2 = importlib.import_module("google.oauth2.credentials")
    monkeypatch.setattr(
        google_oauth2.Credentials,
        "from_authorized_user_file",
        staticmethod(lambda path: None),
    )

    import googleapiclient.discovery as disco

    monkeypatch.setattr(disco, "build", lambda *a, **k: _FakeService())

    ctx = _ctx(confirm=True)
    result = cmod._followup_apply_step(ctx, {"request_id": "r-0042", "supplier_id": "s-1"})

    assert result.ok, result.message
    assert len(upserted) == 1, "upsert must be called exactly once"
    assert upserted[0].shortlist[0].outreach["followup_status"] == "draft_ready"
