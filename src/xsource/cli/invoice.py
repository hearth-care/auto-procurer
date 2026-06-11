"""Invoice capture CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from xsource.config import Config
from xsource.invoices.capture import capture_invoice, import_csv
from xsource.wiring import build_stores

invoice_app = typer.Typer(help="Capture and hand off supplier invoices.")


@invoice_app.command("add")
def add(
    supplier_id: str = typer.Option(..., "--supplier-id"),
    amount_minor: int = typer.Option(..., "--amount-minor"),
    invoice_date: str = typer.Option(..., "--invoice-date"),
    description: str = typer.Option(..., "--description"),
    request_id: str = typer.Option("", "--request-id"),
    invoice_number: str | None = typer.Option(None, "--invoice-number"),
    due_date: str | None = typer.Option(None, "--due-date"),
    currency: str = typer.Option("GBP", "--currency"),
    file_ref: str | None = typer.Option(None, "--file-ref"),
) -> None:
    cfg = Config.from_env()
    suppliers, requests, invoices = build_stores(cfg)
    report = capture_invoice(
        suppliers=suppliers,
        requests=requests,
        invoices=invoices,
        request_id=request_id,
        supplier_id=supplier_id,
        amount_minor=amount_minor,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        description=description,
        source="manual",
        currency=currency,
        file_ref=file_ref,
    )
    typer.echo(
        {
            "invoice_id": report.invoice_id,
            "warnings": report.warnings,
            "variance": report.variance,
        }
    )


@invoice_app.command("import")
def import_(csv_path: Path) -> None:
    cfg = Config.from_env()
    suppliers, requests, invoices = build_stores(cfg)
    typer.echo(import_csv(csv_path, suppliers=suppliers, requests=requests, invoices=invoices))


@invoice_app.command("list")
def list_() -> None:
    cfg = Config.from_env()
    _suppliers, _requests, invoices = build_stores(cfg)
    for invoice in invoices.all():
        typer.echo(
            f"{invoice.id}\t{invoice.status}\t{invoice.supplier_id}\t"
            f"{invoice.amount_minor} {invoice.currency}\t{invoice.invoice_number or ''}"
        )
