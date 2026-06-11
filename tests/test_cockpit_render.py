"""AC-C6-1 — the generated worker's cockpit opens the three-region shell.

A headless render: feed the framework home loop a fake screen + a scripted
"quit" key, capture the single painted frame, and assert all three regions
(pulse / needs-you / toolkit) plus the worker's identity are present. Proves the
generated cockpit entry imports and renders the three-region grammar with no TTY.
"""

from __future__ import annotations

from clonway_cockpit import registry
from rich.console import Console

from xsource.cli import cockpit


class _FakeScreen:
    """Records every frame the loop paints, rendered to plain text."""

    def __init__(self) -> None:
        self.frames: list[str] = []
        self._console = Console(width=120, record=True)

    def update(self, renderable) -> None:
        with self._console.capture() as cap:
            self._console.print(renderable)
        self.frames.append(cap.get())


def _open_once() -> str:
    screen = _FakeScreen()
    # Scripted key: quit immediately after the first paint.
    cockpit.run_cockpit(read_key=lambda: "q", screen=screen)
    assert screen.frames, "cockpit painted no frame"
    return screen.frames[0]


def test_cockpit_opens_three_region_shell() -> None:
    frame = _open_once()
    # The three-region grammar: pulse / needs you / toolkit, each with its label
    # plus the worker's own content (a stub pill, a stub needs item, a worker
    # shelf). Asserting the region labels proves all three regions painted.
    assert "pulse" in frame  # region 1
    assert "needs you" in frame  # region 2
    assert "toolkit" in frame  # region 3
    assert "xsource" in frame  # the worker's identity (header + pulse)
    assert "Ready for new request" in frame
    assert "New request" in frame  # the worker's own shelf label (toolkit)


def test_cockpit_registers_p1_capabilities_and_doctor() -> None:
    cockpit.register_all()
    registered = {s.key for s in registry.get_capabilities()}
    assert {
        "request.new",
        "invoice.capture",
        "request.list",
        "book.search",
        "book.import",
        "book.publish",
        "doctor",
    } <= registered


def test_store_pill_is_error_when_offline(monkeypatch):
    from xsource.cli import cockpit as _cockpit

    class _FakeOfflineStore:
        offline = True

        def all(self):
            return []

    from unittest.mock import MagicMock

    def _patched_status():
        from xsource.config import Config

        cfg = Config.from_env()
        budget = MagicMock()
        budget.level.return_value = "ok"
        budget.spent.return_value = 0.0
        return {
            "cfg": cfg,
            "suppliers": _FakeOfflineStore(),
            "requests": _FakeOfflineStore(),
            "invoices": _FakeOfflineStore(),
            "budget": budget,
        }

    monkeypatch.setattr(_cockpit, "_status", _patched_status)
    state = _cockpit.capture_state()
    store_pill = next(p for p in state.pills if p.label == "store")
    assert store_pill.level == "error"
    assert "not persisting" in store_pill.detail


def test_pending_replies_pill_present_when_nonzero(monkeypatch):
    from unittest.mock import MagicMock

    from xsource.cli import cockpit as _cockpit
    from xsource.store.models import Request

    request = Request(
        id="r-1",
        created_at="2026-06-01T00:00:00+00:00",
        raw_need="plumbing",
        status="open",
        watcher={
            "possible_replies": [
                {"message_id": "m1", "status": "needs_review"},
                {"message_id": "m2", "status": "needs_review"},
            ]
        },
    )

    class _FakeStore:
        offline = False

        def all(self):
            return [request]

    class _EmptyInvoiceStore:
        offline = False

        def all(self):
            return []

    def _patched_status():
        from xsource.config import Config

        cfg = Config.from_env()
        budget = MagicMock()
        budget.level.return_value = "ok"
        budget.spent.return_value = 0.0
        return {
            "cfg": cfg,
            "suppliers": _FakeStore(),
            "requests": _FakeStore(),
            "invoices": _EmptyInvoiceStore(),
            "budget": budget,
        }

    monkeypatch.setattr(_cockpit, "_status", _patched_status)
    state = _cockpit.capture_state()
    pill_labels = {p.label for p in state.pills}
    assert "pending replies" in pill_labels
    pending_pill = next(p for p in state.pills if p.label == "pending replies")
    assert pending_pill.status == "2"
    assert pending_pill.level == "warn"


def test_no_pending_replies_pill_when_zero(monkeypatch):
    from unittest.mock import MagicMock

    from xsource.cli import cockpit as _cockpit

    class _FakeStore:
        offline = False

        def all(self):
            return []

    class _EmptyInvoiceStore:
        offline = False

        def all(self):
            return []

    def _patched_status():
        from xsource.config import Config

        cfg = Config.from_env()
        budget = MagicMock()
        budget.level.return_value = "ok"
        budget.spent.return_value = 0.0
        return {
            "cfg": cfg,
            "suppliers": _FakeStore(),
            "requests": _FakeStore(),
            "invoices": _EmptyInvoiceStore(),
            "budget": budget,
        }

    monkeypatch.setattr(_cockpit, "_status", _patched_status)
    state = _cockpit.capture_state()
    pill_labels = {p.label for p in state.pills}
    assert "pending replies" not in pill_labels


class _Store:
    def __init__(self, records):
        self.records = list(records)
        self.offline = False

    def all(self):
        return self.records


class _Budget:
    def level(self):
        return "ok"

    def spent(self):
        return 0


def test_capture_state_counts_invoices_needing_attention(monkeypatch) -> None:
    from xsource.config import Config
    from xsource.store.models import InvoiceRecord

    cfg = Config(
        home_postcode="TQ12 1AA",
        default_radius_miles=15,
        shortlist_n=5,
        max_places_calls=10,
        max_web_searches=8,
        monthly_budget_gbp=10.0,
        chase_after_days=3,
        poll_seconds=60,
        max_backoff_seconds=300,
        breaker_threshold=10,
        drive_folder_id=None,
        staff_share_group=None,
        state_dir="/tmp/xsource-test",
        model_chain=["claude-sonnet-4-6"],
    )
    monkeypatch.setattr(
        cockpit,
        "_status",
        lambda: {
            "cfg": cfg,
            "suppliers": _Store([]),
            "requests": _Store([]),
            "invoices": _Store(
                [
                    InvoiceRecord(
                        id="i-0001",
                        request_id="",
                        supplier_id="s-0001",
                        amount_minor=1000,
                        invoice_date="2026-06-11",
                        description="Captured",
                        source="manual",
                        status="captured",
                    ),
                    InvoiceRecord(
                        id="i-0002",
                        request_id="",
                        supplier_id="s-0001",
                        amount_minor=1000,
                        invoice_date="2026-06-11",
                        description="Rejected",
                        source="manual",
                        status="rejected",
                    ),
                    InvoiceRecord(
                        id="i-0003",
                        request_id="",
                        supplier_id="s-0001",
                        amount_minor=1000,
                        invoice_date="2026-06-11",
                        description="Acknowledged",
                        source="manual",
                        status="acknowledged",
                    ),
                ]
            ),
            "budget": _Budget(),
        },
    )

    state = cockpit.capture_state()

    invoice_pill = next(pill for pill in state.pills if pill.label == "invoices")
    assert invoice_pill.status == "2"
    assert invoice_pill.level == "warn"
