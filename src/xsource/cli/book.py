"""Supplier black-book CLI."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import typer

from xsource.book.importer import import_csv
from xsource.book.publish import DIRECTORY_TITLE, publish_directory
from xsource.book.search import format_supplier_row, search_suppliers
from xsource.config import Config
from xsource.sheet.client import SheetClient
from xsource.store.remote import StoreOffline
from xsource.wiring import build_directory_state_file, build_stores

book_app = typer.Typer(help="Search, seed, and publish the supplier black book.")


@book_app.command("search")
def search(term: str) -> None:
    cfg = Config.from_env()
    suppliers, _requests, _invoices = build_stores(cfg)
    quarantined = getattr(suppliers, "quarantined", 0)
    if quarantined:
        typer.echo(
            f"warning: {quarantined} corrupt line(s) quarantined in {suppliers.path.name}",
            err=True,
        )
    for supplier in search_suppliers(suppliers.all(), term):
        typer.echo(format_supplier_row(supplier))


@book_app.command("import")
def import_(
    csv_path: Path,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing suppliers."),
) -> None:
    if not csv_path.exists():
        raise typer.BadParameter(f"{csv_path} does not exist")
    cfg = Config.from_env()
    suppliers, _requests, _invoices = build_stores(cfg)
    try:
        report = import_csv(
            csv_path,
            suppliers,
            today=dt.date.today().isoformat(),
            dry_run=dry_run,
        )
    except StoreOffline as exc:
        typer.echo(f"store offline: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(report)


@book_app.command("publish")
def publish() -> None:
    cfg = Config.from_env()
    suppliers, _requests, _invoices = build_stores(cfg)
    supplier_records = suppliers.all()
    if not supplier_records:
        typer.echo("no suppliers to publish", err=True)
        raise typer.Exit(code=1)

    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_SHEETS_TOKEN_PATH"])
    report = publish_directory(
        supplier_records,
        state_file=build_directory_state_file(cfg),
        client=SheetClient(creds),
        title=DIRECTORY_TITLE,
        folder_id=cfg.drive_folder_id,
        share_with=cfg.staff_share_group,
    )
    typer.echo(report)
