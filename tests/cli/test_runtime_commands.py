from __future__ import annotations

from typer.testing import CliRunner

from xsource.cli import app

runner = CliRunner()


class _EmptyStore:
    offline = False

    def all(self):
        return []


class _NoopGmail:
    def list_recent_messages(self):
        return []


def test_watcher_commands_are_registered():
    result = runner.invoke(app, ["watcher", "--help"])

    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "status" in result.stdout


def test_request_sync_command_is_registered():
    result = runner.invoke(app, ["request", "--help"])

    assert result.exit_code == 0
    assert "sync" in result.stdout
    assert "sync-all" in result.stdout


def test_reorder_rejects_unknown_supplier(monkeypatch, tmp_path):
    from xsource.cli import request as req_mod

    class _EmptySuppliers:
        offline = False

        def all(self):
            return []

    class _EmptyRequests:
        offline = False

        def all(self):
            return []

    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(req_mod, "build_stores", lambda cfg: (_EmptySuppliers(), _EmptyRequests()))

    result = runner.invoke(app, ["request", "reorder", "definitely-not-a-supplier"])

    assert result.exit_code != 0


def test_invoice_commands_are_registered():
    result = runner.invoke(app, ["invoice", "--help"])

    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "import" in result.stdout
    assert "list" in result.stdout
    assert "sync-acks" in result.stdout


def test_watcher_run_once_can_idle_without_anthropic_key(monkeypatch, tmp_path):
    from xsource.cli import watcher

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        watcher, "build_stores", lambda cfg: (_EmptyStore(), _EmptyStore(), _EmptyStore())
    )
    monkeypatch.setattr(watcher, "_gmail_service", lambda: object())
    monkeypatch.setattr(watcher, "_sheet_client", lambda: object())
    monkeypatch.setattr(watcher, "GmailWatcherClient", lambda service, own_addresses: _NoopGmail())

    result = runner.invoke(app, ["watcher", "run", "--once"])

    assert result.exit_code == 0
    assert "'processed': 0" in result.stdout
