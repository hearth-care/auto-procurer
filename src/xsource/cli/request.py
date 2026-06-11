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
    suppliers, requests = build_stores(cfg)
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
    suppliers, requests = build_stores(cfg)
    with run_session(trigger="request.sync-all", args={}):
        report = sync_all_requests(
            suppliers=suppliers,
            requests=requests,
            sheets=_sheet_client(),
            synced_at=dt.datetime.now(dt.UTC),
        )
        emit_heartbeat(job_name="request-sync-all", outcome="ok", counts=report)
    typer.echo(report)
