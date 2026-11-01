from __future__ import annotations

from typer.testing import CliRunner

from xsource.cli import app


def test_watcher_run_cycles_and_interval_options(monkeypatch) -> None:
    calls = []

    def process():
        calls.append("tick")
        return {"processed": 1, "possible_replies": 0}

    monkeypatch.setattr("xsource.cli.watcher._process_factory", lambda _cfg: process)

    result = CliRunner().invoke(app, ["watcher", "run", "--cycles", "2", "--interval", "0"])

    assert result.exit_code == 0
    assert calls == ["tick", "tick"]
    assert "processed" in result.stdout


def test_watcher_status_prints_open_requests_and_last_check(monkeypatch, tmp_path):
    from xsource.store.jsonl import JsonlStore
    from xsource.store.models import Request

    store = JsonlStore(tmp_path / "requests.jsonl", Request)
    for request_id, status, watcher in [
        ("r-0001", "open", {"last_checked_at": "2026-09-23T09:58:00+00:00"}),
        ("r-0002", "open", {}),
        ("r-0003", "closed", {}),
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
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr("xsource.cli.watcher.build_stores", lambda cfg: (object(), store, object()))
    result = CliRunner().invoke(app, ["watcher", "status"])
    assert result.exit_code == 0
    assert result.stdout == (
        "open_requests=2\nr-0001 last_checked=2026-09-23T09:58:00+00:00\nr-0002 last_checked=-\n"
    )


def test_a_failed_redraw_still_uploads_the_processed_message_state(monkeypatch, tmp_path):
    import pytest

    from xsource.cli import watcher as cli_watcher
    from xsource.config import Config

    uploads = []

    class FakeSyncedFile:
        def __init__(self, path, blob=None):
            self.path = path

        def hydrate(self):
            pass

        def upload(self):
            uploads.append(self.path.name)

    class Store:
        offline = False

    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("XSOURCE_WORKBOOK_ID", "wb-1")
    monkeypatch.setattr(cli_watcher, "SyncedFile", FakeSyncedFile)
    monkeypatch.setattr(cli_watcher, "build_stores", lambda cfg: (Store(), Store(), None))
    monkeypatch.setattr(cli_watcher, "_gmail_service", lambda: None)
    monkeypatch.setattr(cli_watcher, "_workbook_client", lambda: None)
    monkeypatch.setattr(cli_watcher, "build_log_store", lambda cfg: None)
    monkeypatch.setattr(cli_watcher, "build_drawn_state_file", lambda cfg: None)

    def failing_redraw(**_kw):
        raise RuntimeError("Black book tab renamed")

    def process_once(*, state, redraw_fn, **_kw):
        state.mark_processed("m-1", "parsed")
        redraw_fn()

    monkeypatch.setattr(cli_watcher, "redraw_workbook", failing_redraw)
    monkeypatch.setattr(cli_watcher, "process_once", process_once)

    run_once = cli_watcher._process_factory(Config.from_env())
    with pytest.raises(RuntimeError, match="Black book"):
        run_once()

    assert uploads == ["watcher.sqlite3"]
