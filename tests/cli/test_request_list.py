from typer.testing import CliRunner

from xsource.cli import app
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Request

runner = CliRunner()


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


def test_request_list_prints_pinned_rows(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod

    store = _seeded_requests(tmp_path)
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = runner.invoke(app, ["request", "list"])
    assert result.exit_code == 0
    assert result.stdout == (
        "r-0001\topen\t2026-06-20T10:00:00+00:00\tfence repair\n"
        "r-0002\tclosed\t2026-06-01T09:00:00+00:00\tannual boiler service\n"
    )


def test_request_list_empty_store_prints_nothing(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod

    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = runner.invoke(app, ["request", "list"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_request_list_warns_on_quarantine(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod

    path = tmp_path / "requests.jsonl"
    path.write_text(
        '{"id": "r-0001", "created_at": "2026-06-20T10:00:00+00:00", '
        '"raw_need": "fence repair"}\n'
        "not json\n"
    )
    store = JsonlStore(path, Request)
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (object(), store, object()))
    result = runner.invoke(app, ["request", "list"])
    assert result.exit_code == 0
    assert "warning: 1 corrupt line(s) quarantined in requests.jsonl" in result.stderr
    assert result.stdout.splitlines() == ["r-0001\topen\t2026-06-20T10:00:00+00:00\tfence repair"]
