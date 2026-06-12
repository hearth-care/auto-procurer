from __future__ import annotations

from typer.testing import CliRunner

from xsource.cli import app
from xsource.store.jsonl import JsonlStore
from xsource.store.models import InvoiceRecord, Request, Supplier

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
    monkeypatch.setattr(
        req_mod, "build_stores", lambda cfg: (_EmptySuppliers(), _EmptyRequests(), _EmptyRequests())
    )

    result = runner.invoke(app, ["request", "reorder", "definitely-not-a-supplier"])

    assert result.exit_code != 0


def test_invoice_commands_are_registered():
    result = runner.invoke(app, ["invoice", "--help"])

    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "import" in result.stdout
    assert "list" in result.stdout
    assert "sync-acks" in result.stdout


def _invoice_stores(tmp_path):
    suppliers = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    requests = JsonlStore(tmp_path / "requests.jsonl", Request)
    invoices = JsonlStore(tmp_path / "invoices.jsonl", InvoiceRecord)
    return suppliers, requests, invoices


def test_invoice_add_reports_invalid_date_without_traceback(monkeypatch, tmp_path):
    from xsource.cli import invoice as invoice_mod

    suppliers, requests, invoices = _invoice_stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        invoice_mod, "build_stores", lambda cfg: (suppliers, requests, invoices)
    )

    result = runner.invoke(
        app,
        [
            "invoice",
            "add",
            "--supplier-id",
            "s-0001",
            "--amount-minor",
            "10000",
            "--invoice-date",
            "11/06/2026",
            "--description",
            "Bad date",
            "--invoice-number",
            "INV-BAD",
        ],
    )

    assert result.exit_code == 1
    assert "invalid invoice_date" in result.output
    assert "Traceback" not in result.output
    assert invoices.all() == []


def test_invoice_reemit_reports_invalid_date_without_traceback(monkeypatch, tmp_path):
    from xsource.cli import invoice as invoice_mod

    suppliers, requests, invoices = _invoice_stores(tmp_path)
    suppliers.upsert(Supplier(id="s-0001", name="Smith Heating"))
    invoices.upsert(
        InvoiceRecord(
            id="i-0001",
            request_id="",
            supplier_id="s-0001",
            amount_minor=10000,
            invoice_date="2026-06-11",
            due_date="2026-06-30",
            description="Boiler repair",
            source="manual",
            status="rejected",
        )
    )
    monkeypatch.setenv("XSOURCE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        invoice_mod, "build_stores", lambda cfg: (suppliers, requests, invoices)
    )

    result = runner.invoke(
        app,
        ["invoice", "reemit", "i-0001", "--due-date", "30/06/2026"],
    )

    assert result.exit_code == 1
    assert "invalid due_date" in result.output
    assert "Traceback" not in result.output
    assert invoices.get("i-0001").status == "rejected"


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
