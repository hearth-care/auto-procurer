from __future__ import annotations

import json

from clonway_cockpit.walk import WizardContext
from rich.console import Console

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


def _seeded_requests(tmp_path):
    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    store.upsert(
        Request(
            id="r-0001",
            created_at="2026-06-20T10:00:00+00:00",
            raw_need="fence repair",
        )
    )
    store.upsert(
        Request(
            id="r-0002",
            created_at="2026-06-01T09:00:00+00:00",
            raw_need="annual boiler service",
            status="closed",
        )
    )
    return store


def _alpha_supplier() -> Supplier:
    return Supplier(
        id="s-0001",
        name="Alpha Tree Care",
        categories=["trees-grounds"],
        tags=["tree-surgery"],
        phone="+441632960001",
    )


class _NoWriteStore:
    offline = False
    quarantined = 0

    def __init__(self, inner):
        self.inner = inner
        self.path = inner.path

    def all(self):
        return self.inner.all()

    def upsert(self, rec):
        raise AssertionError("read-only walk attempted to write")


def _online(store):
    store.offline = False
    return store


def test_request_list_step_summary_and_rows(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = _seeded_requests(tmp_path)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = cockpit_mod._request_list_step(_ctx([]), {})
    assert result.ok is True
    assert result.data["summary"] == "1 open · 2 total"


def test_request_list_empty_store_summary(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = cockpit_mod._request_list_step(_ctx([]), {})
    assert result.ok is True
    assert result.data["summary"] == "0 open · 0 total"


def test_request_list_walk_surfaces_quarantine(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    path = tmp_path / "requests.jsonl"
    path.write_text(
        '{"id": "r-0001", "created_at": "2026-06-20T10:00:00+00:00", '
        '"raw_need": "fence repair"}\n'
        "not json\n"
    )
    store = JsonlStore(path, Request)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = cockpit_mod._request_list_step(_ctx([]), {})
    assert result.data["summary"] == "1 open · 1 total · quarantined: 1 corrupt line(s)"


def test_readonly_preconditions_allow_offline_cache(monkeypatch):
    from xsource.cli import cockpit as cockpit_mod

    class _Offline:
        offline = True

    monkeypatch.setattr(
        cockpit_mod,
        "build_stores",
        lambda cfg: (_Offline(), _Offline(), _Offline()),
    )
    rows = cockpit_mod._readonly_preconditions(_ctx([]))
    assert rows[0].ok is True
    assert rows[0].detail == "offline read-only cache"


def test_search_walk_surfaces_quarantine(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    path = tmp_path / "suppliers.jsonl"
    path.write_text(json.dumps(_alpha_supplier().to_dict()) + "\nnot json\n")
    store = JsonlStore(path, Supplier)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = cockpit_mod._book_search_results_step(_ctx([]), {"term": "alpha"})
    assert result.data["summary"] == "1 match(es) for 'alpha' · quarantined: 1 corrupt line(s)"


def test_search_walk_no_matches(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    store.upsert(_alpha_supplier())
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = cockpit_mod._book_search_results_step(_ctx([]), {"term": "roofing"})
    assert result.data["summary"] == "0 match(es) for 'roofing'"


def test_search_walk_empty_book(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = cockpit_mod._book_search_results_step(_ctx([]), {"term": "heating"})
    assert result.data["summary"] == "0 match(es) for 'heating'"


def test_search_term_step_rejects_empty():
    from xsource.cli import cockpit as cockpit_mod

    result = cockpit_mod._book_search_term_step(_ctx([""]), {})
    assert result.ok is False
    assert result.message == "No search term entered."


def test_readonly_walks_never_upsert(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    requests = _NoWriteStore(_seeded_requests(tmp_path))
    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    suppliers.upsert(_alpha_supplier())
    readonly_suppliers = _NoWriteStore(suppliers)
    monkeypatch.setattr(
        cockpit_mod,
        "build_stores",
        lambda cfg: (readonly_suppliers, requests, object()),
    )
    assert cockpit_mod._request_list_step(_ctx([]), {}).ok is True
    assert cockpit_mod._book_search_results_step(_ctx([]), {"term": "alpha"}).ok is True


def test_request_list_walk_result_via_drive(monkeypatch, tmp_path):
    from clonway_cockpit.agent import CockpitDriver

    from xsource.cli import cockpit as cockpit_mod

    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    requests = _seeded_requests(tmp_path)
    suppliers = _online(JsonlStore(tmp_path / "suppliers.jsonl", Supplier))
    invoices = _online(JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord))
    requests = _online(requests)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (suppliers, requests, invoices))
    host = cockpit_mod._host(agent_mode=True)
    stream = CockpitDriver(host, keys=["B", "2", "y"]).run()
    results = [m for m in stream if m.kind == "walk.result"]
    assert results and results[0].meta["ok"] is True
    assert results[0].meta["message"] == "1 open · 2 total"


def _watcher_requests(tmp_path):
    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    for request_id, status, watcher in [
        ("r-0001", "open", {"last_checked_at": "2026-09-23T09:58:00+00:00"}),
        ("r-0002", "open", {}),
        ("r-0003", "closed", {"last_checked_at": "2026-09-24T09:58:00+00:00"}),
    ]:
        store.upsert(
            Request(
                id=request_id,
                created_at="2026-09-23T09:00:00+00:00",
                raw_need="repair",
                status=status,
                watcher=watcher,
            )
        )
    return store


def test_watcher_status_rows_matches_cli_lines(tmp_path):
    from xsource.cli import cockpit

    assert cockpit.watcher_status_rows(_watcher_requests(tmp_path).all()) == [
        "r-0001 last_checked=2026-09-23T09:58:00+00:00",
        "r-0002 last_checked=-",
    ]


def test_watcher_status_step_summary_and_rows(monkeypatch, tmp_path):
    from xsource.cli import cockpit

    store = _watcher_requests(tmp_path)
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: (object(), store, object()))
    result = cockpit._watcher_status_step(_ctx([]), {})
    assert result.ok is True
    assert result.data == {
        "summary": "2 open request(s) watched · last check 2026-09-23T09:58:00+00:00\n"
        "r-0001 last_checked=2026-09-23T09:58:00+00:00\n"
        "r-0002 last_checked=-",
        "rows": ["r-0001 last_checked=2026-09-23T09:58:00+00:00", "r-0002 last_checked=-"],
    }
    request = store.all()[0]
    request.watcher = {}
    store.upsert(request)
    summary = cockpit._watcher_status_step(_ctx([]), {}).data["summary"]
    assert summary.splitlines()[0].endswith("· last check never")


def test_watcher_status_walk_result_via_drive(monkeypatch, tmp_path):
    from clonway_cockpit.agent import CockpitDriver

    from xsource.cli import cockpit

    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    stores = (
        _online(JsonlStore(tmp_path / "suppliers.jsonl", Supplier)),
        _online(_watcher_requests(tmp_path)),
        _online(JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)),
    )
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: stores)
    stream = CockpitDriver(cockpit._host(agent_mode=True), keys=["E", "3", "y"]).run()
    results = [m for m in stream if m.kind == "walk.result"]
    assert results and results[0].meta["ok"] is True
    assert (
        results[0].meta["message"]
        == "2 open request(s) watched · last check 2026-09-23T09:58:00+00:00\n"
        "r-0001 last_checked=2026-09-23T09:58:00+00:00\n"
        "r-0002 last_checked=-"
    )


def test_watcher_status_walk_never_writes(monkeypatch, tmp_path):
    from xsource.cli import cockpit

    store = _NoWriteStore(_watcher_requests(tmp_path))
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: (object(), store, object()))
    assert cockpit._watcher_status_step(_ctx([]), {}).ok is True


def test_watcher_status_empty_and_quarantined(monkeypatch, tmp_path):
    from xsource.cli import cockpit

    path = tmp_path / "requests.jsonl"
    path.write_text("not json\n")
    store = JsonlStore(path, Request)
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: (object(), store, object()))
    assert cockpit._watcher_status_step(_ctx([]), {}).data == {
        "summary": "0 open request(s) watched · last check never · quarantined: 1 corrupt line(s)",
        "rows": [],
    }


def test_watcher_status_rows_with_quarantine(monkeypatch, tmp_path):
    from xsource.cli import cockpit

    store = _watcher_requests(tmp_path)
    with open(store.path, "a") as f:
        f.write("not json\n")
    reloaded = JsonlStore(store.path, Request)
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: (object(), reloaded, object()))
    assert cockpit._watcher_status_step(_ctx([]), {}).data == {
        "summary": "2 open request(s) watched · last check 2026-09-23T09:58:00+00:00"
        " · quarantined: 1 corrupt line(s)\n"
        "r-0001 last_checked=2026-09-23T09:58:00+00:00\n"
        "r-0002 last_checked=-",
        "rows": ["r-0001 last_checked=2026-09-23T09:58:00+00:00", "r-0002 last_checked=-"],
    }
