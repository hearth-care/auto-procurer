"""The lasting procurement workbook: create it, redraw it from the store, move old Sheets in."""

from __future__ import annotations

import datetime as dt
import os

import typer

from xsource.config import Config
from xsource.obs import run_session
from xsource.wiring import build_drawn_state_file, build_log_store, build_stores
from xsource.workbook.client import WorkbookClient
from xsource.workbook.redraw import migrate_open_requests, redraw_workbook, unmigrated

workbook_app = typer.Typer(help="Manage the lasting procurement workbook.")

WORKBOOK_TITLE = "Gareth: procurement"


def _credentials():
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(os.environ["XSOURCE_SHEETS_TOKEN_PATH"])


def _workbook_client() -> WorkbookClient:
    return WorkbookClient(_credentials())


def _legacy_sheets():
    from xsource.sheet.client import SheetClient

    return SheetClient(_credentials())


def _configured_id(cfg: Config) -> str:
    if not cfg.workbook_id:
        raise typer.BadParameter(
            "XSOURCE_WORKBOOK_ID is not set; run `xsource workbook init` first"
        )
    return cfg.workbook_id


@workbook_app.command("init")
def init() -> None:
    cfg = Config.from_env()
    client = _workbook_client()
    workbook_id, url = client.create(WORKBOOK_TITLE, cfg.drive_folder_id)
    tabs = client.tab_ids(workbook_id)
    client.format_tab(workbook_id, tabs["Board"], "board")
    client.format_tab(workbook_id, tabs["Black book"], "black_book")
    client.format_tab(workbook_id, tabs["Log"], "log")
    typer.echo(f"export XSOURCE_WORKBOOK_ID={workbook_id}")
    typer.echo(url)


@workbook_app.command("redraw")
def redraw() -> None:
    cfg = Config.from_env()
    workbook_id = _configured_id(cfg)
    suppliers, requests, _invoices = build_stores(cfg)
    with run_session(trigger="workbook.redraw", args={}):
        report = redraw_workbook(
            workbook_id=workbook_id,
            client=_workbook_client(),
            suppliers=suppliers,
            requests=requests,
            log=build_log_store(cfg),
            drawn_file=build_drawn_state_file(cfg),
            now=dt.datetime.now(dt.UTC),
        )
    typer.echo(report)


@workbook_app.command("migrate")
def migrate(
    apply: bool = typer.Option(False, "--apply", help="Move the requests; without it, list them."),
) -> None:
    cfg = Config.from_env()
    workbook_id = _configured_id(cfg)
    suppliers, requests, _invoices = build_stores(cfg)
    pending = unmigrated(requests)
    if not apply:
        for r in pending:
            typer.echo(f"{r.id}\t{r.sheet_id}\twould move into the workbook")
        typer.echo(f"{len(pending)} open request(s) to move; run again with --apply")
        return
    client, log, drawn_file = _workbook_client(), build_log_store(cfg), build_drawn_state_file(cfg)
    now = dt.datetime.now(dt.UTC)
    with run_session(trigger="workbook.migrate", args={}):
        for line in migrate_open_requests(
            workbook_id=workbook_id,
            client=client,
            legacy_sheets=_legacy_sheets(),
            suppliers=suppliers,
            requests=requests,
            log=log,
            drawn_file=drawn_file,
            now=now,
        ):
            typer.echo(line)
        report = redraw_workbook(
            workbook_id=workbook_id,
            client=client,
            suppliers=suppliers,
            requests=requests,
            log=log,
            drawn_file=drawn_file,
            now=now,
        )
    typer.echo(report)
