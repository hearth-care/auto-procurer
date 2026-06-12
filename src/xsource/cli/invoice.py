"""Invoice capture CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from xsource.config import Config
from xsource.invoices.acks import ingest_ack_records, read_ack_jsonl
from xsource.invoices.capture import (
    capture_invoice,
    import_csv,
    reemit_invoice,
    write_off_invoice,
)
from xsource.wiring import build_stores

invoice_app = typer.Typer(help="Capture and hand off supplier invoices.")
_ACK_PATH_ARG = typer.Argument(
    None,
    help="JSONL ack file; defaults to XSOURCE_STATE_DIR/payment-required-acks.jsonl.",
)


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


@invoice_app.command("reemit")
def reemit(
    invoice_id: str = typer.Argument(..., help="Id of a rejected invoice to correct and re-emit."),
    amount_minor: int | None = typer.Option(None, "--amount-minor"),
    invoice_date: str | None = typer.Option(None, "--invoice-date"),
    due_date: str | None = typer.Option(None, "--due-date"),
    description: str | None = typer.Option(None, "--description"),
    invoice_number: str | None = typer.Option(None, "--invoice-number"),
) -> None:
    """Correct a rejected invoice and return it to the emittable lifecycle."""
    cfg = Config.from_env()
    suppliers, _requests, invoices = build_stores(cfg)
    invoice = reemit_invoice(
        invoices,
        invoice_id,
        suppliers=suppliers,
        amount_minor=amount_minor,
        invoice_date=invoice_date,
        due_date=due_date,
        description=description,
        invoice_number=invoice_number,
    )
    typer.echo({"invoice_id": invoice.id, "status": invoice.status})


@invoice_app.command("write-off")
def write_off(
    invoice_id: str = typer.Argument(..., help="Id of a rejected invoice to write off."),
) -> None:
    """Mark a rejected invoice written off (it will never be re-emitted)."""
    cfg = Config.from_env()
    _suppliers, _requests, invoices = build_stores(cfg)
    invoice = write_off_invoice(invoices, invoice_id)
    typer.echo({"invoice_id": invoice.id, "status": invoice.status})


@invoice_app.command("sync-acks")
def sync_acks(ack_path: Path | None = _ACK_PATH_ARG) -> None:
    cfg = Config.from_env()
    _suppliers, _requests, invoices = build_stores(cfg)
    path = ack_path or Path(cfg.state_dir) / "payment-required-acks.jsonl"
    typer.echo(ingest_ack_records(invoices, read_ack_jsonl(path)))
