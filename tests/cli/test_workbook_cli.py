from typer.testing import CliRunner
from workbook.fakes import FakeStore, FakeWorkbookClient

from xsource.cli import app
from xsource.cli import workbook as cli_workbook
from xsource.store.models import Request, ShortlistEntry, Supplier

runner = CliRunner()


class _Creator(FakeWorkbookClient):
    def create(self, title, folder_id):
        self.calls.append(("create", folder_id))
        return "wb-new", "https://example.test/wb-new"


def test_init_creates_formats_each_fixed_tab_once_and_prints_the_id(monkeypatch):
    client = _Creator()
    monkeypatch.setenv("XSOURCE_DRIVE_FOLDER_ID", "folder-1")
    monkeypatch.setattr(cli_workbook, "_workbook_client", lambda: client)
    monkeypatch.setattr(
        cli_workbook, "build_stores", lambda cfg: (_ for _ in ()).throw(AssertionError("store"))
    )
    result = runner.invoke(app, ["workbook", "init"])
    assert result.exit_code == 0
    assert "export XSOURCE_WORKBOOK_ID=wb-new" in result.stdout
    assert "https://example.test/wb-new" in result.stdout
    assert client.calls == [("create", "folder-1")]
    assert client.formatted == [(0, "board"), (1, "black_book"), (2, "log")]


def test_redraw_needs_a_configured_workbook(monkeypatch):
    monkeypatch.delenv("XSOURCE_WORKBOOK_ID", raising=False)
    result = runner.invoke(app, ["workbook", "redraw"])
    assert result.exit_code != 0


def test_redraw_command_redraws_the_configured_workbook(monkeypatch, tmp_path):
    monkeypatch.setenv("XSOURCE_WORKBOOK_ID", "wb")
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    client = FakeWorkbookClient()
    monkeypatch.setattr(cli_workbook, "_workbook_client", lambda: client)
    result = runner.invoke(app, ["workbook", "redraw"])
    assert result.exit_code == 0, result.output
    assert "'jobs': 0" in result.stdout
    assert [n for c, n in client.calls if c == "write_tab"] == ["Board", "Black book", "Log"]


def test_sync_all_redraws_the_workbook_when_one_is_configured(monkeypatch, tmp_path):
    from xsource.cli import request as cli_request

    monkeypatch.setenv("XSOURCE_WORKBOOK_ID", "wb")
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    client = FakeWorkbookClient()
    monkeypatch.setattr(cli_workbook, "_workbook_client", lambda: client)
    monkeypatch.setattr(
        cli_request, "_sheet_client", lambda: (_ for _ in ()).throw(AssertionError("legacy"))
    )
    result = runner.invoke(app, ["request", "sync-all"])
    assert result.exit_code == 0, result.output
    assert ("write_tab", "Board") in client.calls


def test_migrate_apply_moves_requests_then_redraws(monkeypatch, tmp_path):
    class Legacy:
        def read_request_rows(self, sheet_id):
            return []

    req = Request(
        id="r-old",
        created_at="2026-10-01T09:00:00+00:00",
        raw_need="old thing",
        sheet_id="old-sheet",
        triage={"category": "Boiler service"},
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],
    )
    requests, client = FakeStore([req]), FakeWorkbookClient()
    suppliers = FakeStore([Supplier(id="s-1", name="Acme Testing")])
    monkeypatch.setenv("XSOURCE_WORKBOOK_ID", "wb")
    monkeypatch.setattr(cli_workbook, "build_stores", lambda cfg: (suppliers, requests, None))
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(cli_workbook, "build_log_store", lambda cfg: FakeStore())
    monkeypatch.setattr(cli_workbook, "_workbook_client", lambda: client)
    monkeypatch.setattr(cli_workbook, "_legacy_sheets", lambda: Legacy())
    result = runner.invoke(app, ["workbook", "migrate", "--apply"])
    assert result.exit_code == 0, result.output
    assert requests.get("r-old").job_tab == "Boiler service Oct 2026"
    assert client.formatted == [(3, "job")]
    assert ("write_tab", "Boiler service Oct 2026") in client.calls
