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
