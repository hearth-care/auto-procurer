"""Request lifecycle CLI."""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import typer

from xsource.config import Config
from xsource.obs import run_session
from xsource.runtime import emit_heartbeat
from xsource.sheet.client import SheetClient
from xsource.sheet.sync import apply_sheet_rows
from xsource.wiring import build_stores

request_app = typer.Typer(help="Manage xsource procurement requests.")


def _sheet_client() -> SheetClient:
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_SHEETS_TOKEN_PATH"])
    return SheetClient(creds)


def sync_one_request(*, request, suppliers, requests, sheets, synced_at: dt.datetime):
    rows = sheets.read_request_rows(request.sheet_id)
    report = apply_sheet_rows(request, rows, suppliers=suppliers, synced_at=synced_at)
    requests.upsert(request)
    return report


def sync_all_requests(*, suppliers, requests, sheets, synced_at: dt.datetime) -> dict[str, Any]:
    report: dict[str, Any] = {"synced_requests": 0, "updated_suppliers": 0, "warnings": []}
    for request in requests.all():
        if request.status != "open":
            continue
        if not request.sheet_id:
            report["warnings"].append(f"{request.id} has no sheet_id")
            continue
        one = sync_one_request(
            request=request,
            suppliers=suppliers,
            requests=requests,
            sheets=sheets,
            synced_at=synced_at,
        )
        report["synced_requests"] += 1
        report["updated_suppliers"] += one["updated_suppliers"]
        report["warnings"].extend(one["warnings"])
    return report


@request_app.command("sync")
def sync(request_id: str) -> None:
    cfg = Config.from_env()
    suppliers, requests, _invoices = build_stores(cfg)
    with run_session(trigger="request.sync", args={"request_id": request_id}):
        request = requests.get(request_id)
        if request is None:
            raise typer.BadParameter(f"unknown request id {request_id}")
        if not request.sheet_id:
            raise typer.BadParameter(f"request {request_id} has no sheet_id")
        report = sync_one_request(
            request=request,
            suppliers=suppliers,
            requests=requests,
            sheets=_sheet_client(),
            synced_at=dt.datetime.now(dt.UTC),
        )
        emit_heartbeat(job_name="request-sync", outcome="ok", counts=report)
    typer.echo(report)


@request_app.command("sync-all")
def sync_all() -> None:
    cfg = Config.from_env()
    suppliers, requests, _invoices = build_stores(cfg)
    with run_session(trigger="request.sync-all", args={}):
        report = sync_all_requests(
            suppliers=suppliers,
            requests=requests,
            sheets=_sheet_client(),
            synced_at=dt.datetime.now(dt.UTC),
        )
        emit_heartbeat(job_name="request-sync-all", outcome="ok", counts=report)
    typer.echo(report)


@request_app.command("trigger")
def trigger(
    file: typer.FileText = typer.Option(  # noqa: B008
        None, "--file", "-f", help="JSON payload file ({source, subject?, body})."
    ),
) -> None:
    """Parse an email/chat trigger and show what was extracted."""
    import json
    import sys

    from xsource.p4.triggers import parse_trigger

    raw = file.read() if file is not None else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    parsed = parse_trigger(payload)
    if parsed is None:
        typer.echo("Not a procurement trigger.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"source: {parsed.constraints.get('source', 'unknown')}")
    typer.echo(f"need:   {parsed.raw_need}")


@request_app.command("followup")
def followup(
    request_id: str,
    supplier_id: str,
) -> None:
    """Create a draft follow-up reply for a supplier response (opens cockpit)."""
    from xsource.cli.cockpit import run_cockpit

    cfg = Config.from_env()
    suppliers, requests_, _invoices = build_stores(cfg)
    request = requests_.get(request_id)
    if request is None:
        raise typer.BadParameter(f"unknown request id {request_id}")
    supplier = next((s for s in suppliers.all() if s.id == supplier_id), None)
    if supplier is None:
        raise typer.BadParameter(f"unknown supplier id {supplier_id}")
    if not any(entry.supplier_id == supplier_id and entry.reply for entry in request.shortlist):
        raise typer.BadParameter(
            f"supplier {supplier_id} has no recorded reply on request {request_id}"
        )

    run_cockpit(focus=f"request.followup:{request_id}:{supplier_id}")


@request_app.command("reorder")
def reorder(supplier_id: str) -> None:
    """Open a prefilled reorder review for a recurring supplier (opens cockpit)."""
    from xsource.cli.cockpit import run_cockpit

    cfg = Config.from_env()
    suppliers, _requests, _invoices = build_stores(cfg)
    supplier = next((s for s in suppliers.all() if s.id == supplier_id), None)
    if supplier is None:
        raise typer.BadParameter(f"unknown supplier id {supplier_id}")

    run_cockpit(focus=f"request.reorder:{supplier_id}")
