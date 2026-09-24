from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from clonway_cockpit.agent import CockpitDriver

from xsource.cli import cockpit
from xsource.config import Config
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, ShortlistEntry, Supplier

NOW = dt.datetime(2026, 9, 23, 12, tzinfo=dt.UTC)


@pytest.fixture
def report(monkeypatch, tmp_path):
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("XSOURCE_EMIT_SIGNALS", raising=False)
    monkeypatch.setattr(cockpit, "_utc_now", lambda: NOW, raising=False)
    monkeypatch.setattr(cockpit, "build_xsource_signals", lambda **kw: (), raising=False)
    stores = [
        JsonlStore(tmp_path / f"{name}.jsonl", model)
        for name, model in [
            ("suppliers", Supplier),
            ("requests", Request),
            ("invoices", InvoiceRecord),
        ]
    ]
    for store in stores:
        store.offline = False
    return dict(
        cfg=Config.from_env(),
        suppliers=stores[0],
        requests=stores[1],
        invoices=stores[2],
        budget=SimpleNamespace(level=lambda: "ok", spent=lambda: 0.0),
    )


def _probe(report, name):
    return next(probe for probe in cockpit.doctor_build_probes(report) if probe.name == name)


def _request(report, checked=None, thread=True, status="open", request_id="r-0001"):
    request = Request(
        id=request_id,
        created_at=NOW.isoformat(),
        raw_need="repair",
        status=status,
        watcher={"last_checked_at": checked} if checked else {},
        shortlist=[ShortlistEntry(supplier_id="s-0001", rank=1, outreach={"thread_id": "t-1"})]
        if thread
        else [],
    )
    report["requests"].upsert(request)


def test_doctor_probe_names_in_order(report):
    probes = cockpit.doctor_build_probes(report)
    assert [p.name for p in probes] == [
        "Google Maps key",
        "Anthropic key",
        "Sheets token",
        "Store",
        "Budget",
        "Home postcode",
        "Store records",
        "Reply watcher",
        "Pending signals",
    ]
    assert all(p.fix is None for p in probes[-3:])


def test_store_records_probe_counts(report):
    report["suppliers"].upsert(Supplier(id="s-0001", name="Example Maintenance"))
    for n in range(3):
        _request(report, request_id=f"r-{n:04d}")
    probe = _probe(report, "Store records")
    assert (probe.level, probe.detail) == ("ok", "1 supplier(s) · 3 request(s) · 0 invoice(s)")


@pytest.mark.parametrize("missing", ["suppliers", "requests", "invoices"])
def test_store_records_probe_unavailable(report, missing, monkeypatch):
    def fail_if_called(**kw):
        raise AssertionError("build_xsource_signals must not run when a store is unavailable")

    monkeypatch.setattr(cockpit, "build_xsource_signals", fail_if_called)
    report[missing] = None
    probe = _probe(report, "Store records")
    assert (probe.level, probe.detail) == ("warn", "store unavailable")
    if missing == "requests":
        probe = _probe(report, "Reply watcher")
        assert (probe.level, probe.detail) == ("warn", "store unavailable")
    probe = _probe(report, "Pending signals")
    assert (probe.level, probe.detail) == ("warn", "store unavailable")


@pytest.mark.parametrize(
    "checked", [None, "2026-09-23T09:00:00+00:00", "2026-09-23T10:00:00+00:00"]
)
def test_reply_watcher_probe_stale(report, checked):
    _request(report, checked)
    probe = _probe(report, "Reply watcher")
    assert (probe.level, probe.detail) == ("error", "1 live outreach thread(s), watcher stale.")


def test_reply_watcher_probe_fresh(report):
    _request(report, "2026-09-23T11:30:00+00:00")
    probe = _probe(report, "Reply watcher")
    assert (probe.level, probe.detail) == ("ok", "fresh · 1 open request(s) watched")


@pytest.mark.parametrize("status,thread", [("open", False), ("closed", True)])
def test_reply_watcher_probe_nothing_to_watch(report, status, thread):
    _request(report, thread=thread, status=status)
    probe = _probe(report, "Reply watcher")
    assert (probe.level, probe.detail) == ("ok", "no live outreach threads")


@pytest.mark.parametrize("count", [0, 2])
@pytest.mark.parametrize("enabled", [False, True])
def test_pending_signals_probe(report, monkeypatch, count, enabled):
    def signals(*, today, now):
        assert today == NOW.date() and now == NOW
        return [object()] * count

    monkeypatch.setattr(cockpit, "build_xsource_signals", signals)
    monkeypatch.setenv("XSOURCE_EMIT_SIGNALS", "1" if enabled else "0")
    probe = _probe(report, "Pending signals")
    assert probe.level == ("warn" if count else "ok")
    assert probe.detail == f"{count} raised · " + (
        "emission enabled" if enabled else "not sent (XSOURCE_EMIT_SIGNALS off)"
    )


def test_doctor_frame_lists_new_probes_via_drive(report, monkeypatch):
    monkeypatch.setattr(
        cockpit,
        "build_stores",
        lambda cfg: (report["suppliers"], report["requests"], report["invoices"]),
    )
    monkeypatch.setattr(cockpit, "build_budget", lambda *args: report["budget"])
    stream = CockpitDriver(cockpit._host(agent_mode=True), keys=["G", "q"]).run()
    frame = next(frame for frame in stream if frame.kind == "doctor")
    region = next(region for region in frame.regions if region.role == "probes")
    assert [row.label for row in region.rows][-3:] == [
        "Store records",
        "Reply watcher",
        "Pending signals",
    ]
