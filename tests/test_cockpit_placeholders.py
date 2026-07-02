"""Placeholder-card affordance tests.

Verifies that every ``run=None`` capability carries explicit status wording so a
rendered card is self-describing (Phase 2 of the cockpit journey-map plan).

Drive-based assertions use ``CockpitDriver`` + the structured ``ScreenModel``
(``meta['summary']``) — never ``export_text()``. Registry assertions cover
capabilities whose cards crash when driven (``equivalent_cli=None`` hits a
framework ``chip()`` bug) and are equally valid: they check the registered
data, not rendered pixels.
"""

from __future__ import annotations

import pytest
from clonway_cockpit import registry
from clonway_cockpit.agent import CockpitDriver

from xsource.cli import cockpit

# Keys that mark a capability card as self-describing.
_PLANNED_MARKER = "Planned — not yet wired."
_CLI_MARKER = "Read-only via CLI:"
_BUILD_ONLY_MARKER = "Build-only"
_LIVE_MARKER = "Live"

_PLACEHOLDER_STATUS_MARKERS = {
    "book.import": _PLANNED_MARKER,
    "book.publish": _PLANNED_MARKER,
    "request.sync": _CLI_MARKER,
    "watcher.status": _CLI_MARKER,
    "partner.checkatrade": _BUILD_ONLY_MARKER,
    "doctor": _LIVE_MARKER,
}


@pytest.fixture(autouse=True)
def _registered(monkeypatch):
    """Ensure a clean registry populated by register_all() for each test."""
    registry.clear_capabilities()
    cockpit.register_all()
    yield
    registry.clear_capabilities()


def test_placeholder_summaries_carry_status_wording():
    """Every run=None capability summary carries an explicit status marker."""
    caps = {c.key: c for c in registry.get_capabilities() if c.run is None}
    for key, marker in _PLACEHOLDER_STATUS_MARKERS.items():
        assert key in caps, f"Capability {key!r} not in registry"
        summary = caps[key].summary
        assert marker in summary, (
            f"Capability {key!r} summary does not contain {marker!r}; got: {summary!r}"
        )


def test_request_sync_card_summary_via_drive():
    """Drive into the request.sync card and assert status wording in the model frame."""
    host = cockpit._host(agent_mode=True)
    # Shelf B: item 1 = invoice.capture, item 2 = request.list, item 3 = request.sync
    stream = CockpitDriver(host, keys=["B", "3", "q", "q"]).run()
    cards = [m for m in stream if m.kind == "card"]
    assert cards, "No card frame reached after driving to shelf B item 3"
    card = cards[0]
    summary = card.meta.get("summary", "")
    assert _CLI_MARKER in summary, (
        f"request.sync card summary missing {_CLI_MARKER!r}; got: {summary!r}"
    )
    cli = card.meta.get("equivalent_cli", "")
    assert cli.startswith("xsource"), (
        f"request.sync equivalent_cli does not start with 'xsource'; got: {cli!r}"
    )


def test_watcher_status_card_summary_via_drive():
    """Drive into the watcher.status card and assert status wording in the model frame."""
    host = cockpit._host(agent_mode=True)
    # Shelf E: item 1 = request.outreach, item 2 = request.followup, item 3 = watcher.status
    stream = CockpitDriver(host, keys=["E", "3", "q", "q"]).run()
    cards = [m for m in stream if m.kind == "card"]
    assert cards, "No card frame reached after driving to shelf E item 3"
    card = cards[0]
    summary = card.meta.get("summary", "")
    assert _CLI_MARKER in summary, (
        f"watcher.status card summary missing {_CLI_MARKER!r}; got: {summary!r}"
    )
    cli = card.meta.get("equivalent_cli", "")
    assert cli.startswith("xsource"), (
        f"watcher.status equivalent_cli does not start with 'xsource'; got: {cli!r}"
    )


def test_shelf_item_order_is_stable():
    by_shelf: dict[str, list[str]] = {}
    for cap in registry.get_capabilities():
        by_shelf.setdefault(cap.shelf, []).append(cap.key)
    assert by_shelf["A"] == ["request.new", "request.trigger", "request.reorder"]
    assert by_shelf["B"] == ["invoice.capture", "request.list", "request.sync"]
    assert by_shelf["C"] == ["book.search", "book.import"]
    assert by_shelf["D"] == ["book.publish", "partner.checkatrade"]
    assert by_shelf["E"] == ["request.outreach", "request.followup", "watcher.status"]
