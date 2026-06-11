"""Watcher daemon CLI."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

import typer

from xsource.cli.cockpit import _AnthropicStructuredGateway
from xsource.config import Config
from xsource.obs import event as obs_event
from xsource.sheet.client import SheetClient
from xsource.store.remote import StoreOffline
from xsource.watcher.daemon import process_once
from xsource.watcher.gmail import GmailWatcherClient
from xsource.watcher.loop import run_loop
from xsource.watcher.state import ProcessedMessageStore
from xsource.wiring import build_stores

watcher_app = typer.Typer(help="Run or inspect the xsource reply watcher.")


class _LazyStructuredGateway:
    def __init__(self) -> None:
        self._gateway: Any | None = None

    def complete_structured(self, messages, schema, role: str = "research") -> dict:
        if self._gateway is None:
            self._gateway = _AnthropicStructuredGateway()
        return self._gateway.complete_structured(messages, schema, role=role)


def _gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_GMAIL_TOKEN_PATH"])
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _sheet_client() -> SheetClient:
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_SHEETS_TOKEN_PATH"])
    return SheetClient(creds)


def _process_factory(cfg: Config):
    suppliers, requests = build_stores(cfg)
    own_addresses = {
        item.strip().lower()
        for item in os.environ.get("XSOURCE_OWN_EMAILS", "milo.garth@clonwaycare.co.uk").split(",")
        if item.strip()
    }
    state = ProcessedMessageStore(Path(cfg.state_dir) / "watcher.sqlite3")
    gmail = GmailWatcherClient(_gmail_service(), own_addresses=own_addresses)
    sheets = _sheet_client()
    gateway = _LazyStructuredGateway()

    def _run_once():
        # Fail fast when the store is offline — no point processing messages we
        # cannot persist.  This also counts toward the circuit breaker.
        if suppliers.offline or requests.offline:
            obs_event(
                "watcher.store_offline",
                severity="error",
                detail="store offline at cycle start; skipping message processing",
            )
            raise StoreOffline("store is offline — skipping watcher cycle")
        return process_once(
            requests=requests,
            suppliers=suppliers,
            gmail=gmail,
            sheets=sheets,
            gateway=gateway,
            state=state,
            now=dt.datetime.now(dt.UTC),
        )

    return _run_once


def _on_breaker_open(consecutive_failures: int) -> None:
    obs_event(
        "watcher.circuit_breaker_open",
        severity="error",
        consecutive_failures=consecutive_failures,
        detail=f"watcher circuit breaker opened after {consecutive_failures} consecutive failures",
    )
    typer.echo(
        f"FATAL: watcher circuit breaker opened after {consecutive_failures} consecutive"
        " failures — exiting so the supervisor can restart.",
        err=True,
    )


@watcher_app.command("run")
def run(once: bool = typer.Option(False, "--once", help="Run a single watcher cycle.")) -> None:
    cfg = Config.from_env()
    process = _process_factory(cfg)
    if once:
        typer.echo(process())
        return
    run_loop(
        process,
        poll_seconds=cfg.poll_seconds,
        on_error=lambda exc: typer.echo(f"watcher cycle failed: {exc}", err=True),
        max_backoff_seconds=cfg.max_backoff_seconds,
        breaker_threshold=cfg.breaker_threshold,
        on_breaker_open=_on_breaker_open,
    )


@watcher_app.command("status")
def status() -> None:
    cfg = Config.from_env()
    _suppliers, requests = build_stores(cfg)
    open_requests = [request for request in requests.all() if request.status == "open"]
    typer.echo(f"open_requests={len(open_requests)}")
    for request in open_requests:
        typer.echo(f"{request.id} last_checked={request.watcher.get('last_checked_at', '-')}")
