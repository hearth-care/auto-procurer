from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from clonway_cockpit.agent import CockpitDriver

from xsource.cli import cockpit
from xsource.config import Config
from xsource.signals import build as signals_build
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, ShortlistEntry, Supplier

NOW = dt.datetime(2026, 9, 23, 12, tzinfo=dt.UTC)


@pytest.fixture
def report(monkeypatch, tmp_path):
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("XSOURCE_EMIT_SIGNALS", raising=False)
    monkeypatch.setattr(cockpit, "_utc_now", lambda: NOW, raising=False)
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
def test_store_records_probe_unavailable(report, missing):
    report[missing] = None
    probe = _probe(report, "Store records")
    assert (probe.level, probe.detail) == ("warn", "store unavailable")
    if missing == "requests":
        probe = _probe(report, "Reply watcher")
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


_BUILDERS = sorted(
    name
    for name in dir(signals_build)
    if name.startswith("build_") and name.endswith("_signals") and name != "build_xsource_signals"
)


def _chase_due(report):
    # Asked five days before NOW with no reply: the chase-quote builder raises one signal.
    report["requests"].upsert(
        Request(
            id="r-0001",
            created_at="2026-09-18T09:00:00+00:00",
            raw_need="repair",
            watcher={"last_checked_at": "2026-09-23T11:30:00+00:00"},
            shortlist=[
                ShortlistEntry(
                    supplier_id="s-0001",
                    rank=1,
                    outreach={"thread_id": "t-1", "asked_at": "2026-09-18T09:00:00+00:00"},
                )
            ],
        )
    )


def _set_offline(report):
    _chase_due(report)
    for name in ("suppliers", "requests", "invoices"):
        report[name].offline = True


def _raiser(name):
    def arrange(report, monkeypatch):
        _chase_due(report)

        def fail(*args, **kwargs):
            raise OSError("simulated builder failure")

        monkeypatch.setattr(signals_build, name, fail)

    return arrange


# Every state the pending-signal scan can end in, with the level and count it must show.
# None as the count means the probe must not claim a number at all.
_SCAN_OUTCOMES = {
    "empty": (lambda report, mp: None, "ok", 0),
    "nonempty": (lambda report, mp: _chase_due(report), "warn", 1),
    "offline-readable": (lambda report, mp: _set_offline(report), "warn", 2),
    **{
        f"{name}-missing": (
            lambda report, mp, name=name: report.__setitem__(name, None),
            "warn",
            None,
        )
        for name in ("suppliers", "requests", "invoices")
    },
    **{f"{name}-raises": (_raiser(name), "error", None) for name in _BUILDERS},
}


def _doctor_row(report, monkeypatch, name):
    monkeypatch.setattr(
        cockpit,
        "build_stores",
        lambda cfg: (report["suppliers"], report["requests"], report["invoices"]),
    )
    monkeypatch.setattr(cockpit, "build_budget", lambda *args: report["budget"])
    stream = CockpitDriver(cockpit._host(agent_mode=True), keys=["G", "q"]).run()
    frame = next(frame for frame in stream if frame.kind == "doctor")
    rows = next(region.rows for region in frame.regions if region.role == "probes")
    row = next(row for row in rows if row.label == name)
    return {field.label: field.value for field in row.fields}


def test_scan_outcomes_cover_every_signal_builder():
    # Seven builders feed the nightly scan today; a new one must get a failure cell below.
    assert len(_BUILDERS) == 7
    assert {f"{name}-raises" for name in _BUILDERS} <= set(_SCAN_OUTCOMES)


@pytest.mark.parametrize("outcome", sorted(_SCAN_OUTCOMES))
@pytest.mark.parametrize("enabled", [False, True])
def test_pending_signals_probe_outcomes(report, monkeypatch, outcome, enabled):
    arrange, level, count = _SCAN_OUTCOMES[outcome]
    arrange(report, monkeypatch)
    monkeypatch.setenv("XSOURCE_EMIT_SIGNALS", "1" if enabled else "0")
    fields = _doctor_row(report, monkeypatch, "Pending signals")
    emission = "emission enabled" if enabled else "not sent (XSOURCE_EMIT_SIGNALS off)"
    if outcome.endswith("-missing"):
        expected = "store unavailable"
    elif count is None:
        expected = "scan failed (OSError) · count unavailable"
    else:
        expected = f"{count} raised · {emission}"
    assert fields == {"level": level, "detail": expected}


def test_pending_signals_count_matches_nightly_scan(report, monkeypatch):
    # The Doctor counts over its own loaded snapshot; on a readable store that must equal
    # what the nightly emitter's composed scan raises from the same data.
    _set_offline(report)
    monkeypatch.setattr(
        signals_build,
        "build_stores",
        lambda cfg: (report["suppliers"], report["requests"], report["invoices"]),
    )
    nightly = signals_build.build_xsource_signals(today=NOW.date(), now=NOW)
    assert len(nightly) == 2
    assert _probe(report, "Pending signals").detail.startswith(f"{len(nightly)} raised")


def test_pending_signals_ignores_nightly_scan_reload_failure(report, monkeypatch):
    # The nightly scan re-reads the stores and turns any failure into an empty result. The
    # Doctor must not inherit that: it counts from the snapshot it has already loaded.
    _chase_due(report)

    def unavailable(cfg):
        raise OSError("simulated store read failure")

    monkeypatch.setattr(signals_build, "build_stores", unavailable)
    probe = _probe(report, "Pending signals")
    assert (probe.level, probe.detail) == ("warn", "1 raised · not sent (XSOURCE_EMIT_SIGNALS off)")


def test_reply_watcher_probe_check_failed(report, monkeypatch):
    _request(report, "2026-09-23T11:30:00+00:00")

    def fail(*args, **kwargs):
        raise ValueError("simulated builder failure")

    monkeypatch.setattr(signals_build, "build_watcher_health_signals", fail)
    fields = _doctor_row(report, monkeypatch, "Reply watcher")
    assert fields == {"level": "error", "detail": "check failed (ValueError)"}


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
