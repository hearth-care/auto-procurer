from __future__ import annotations

from typer.testing import CliRunner

from xsource.cli import app

runner = CliRunner()


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
