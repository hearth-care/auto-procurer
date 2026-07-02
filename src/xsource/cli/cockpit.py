"""xsource's cockpit: the interactive operations surface."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any, cast

from clonway_cockpit import keys, render, shell, usage
from clonway_cockpit.doctor import Fix, Probe, fixes_for
from clonway_cockpit.prompts import default_confirm_fn, make_clean_input_fn
from clonway_cockpit.registry import (
    BlastRadius,
    CapabilitySpec,
    WizardContext,
    register_capability,
)
from clonway_cockpit.state import CockpitState, NeedsItem, Pill
from clonway_cockpit.walk import Precondition, Step, StepResult, confirm_apply, make_walk_handler
from rich.console import Console, RenderableType

from xsource.book.search import find_matches, format_supplier_row, search_suppliers
from xsource.budget import Budget
from xsource.cli.request import format_request_row
from xsource.config import Config
from xsource.invoices.capture import validate_iso_date
from xsource.research.candidates import Candidate
from xsource.research.pipeline import RunCaps, run_research
from xsource.research.triage import Triage, run_triage
from xsource.secrets import secret_from_env
from xsource.sheet.client import SheetClient
from xsource.signals import emit as signals_emit
from xsource.store.remote import SyncedStore, get_offline_reason
from xsource.wiring import build_budget, build_research_fns, build_stores

_APP_LABEL = "xsource"

_CLI_REQUEST_LIST = "xsource request list"
_CLI_BOOK_SEARCH = "xsource book search"
_CLI_BOOK_IMPORT = "xsource book import"
_CLI_BOOK_PUBLISH = "xsource book publish"

_SHELVES: dict[str, str] = {
    "A": "New request",
    "B": "Requests",
    "C": "Black book",
    "D": "Publish",
    "E": "Outreach",
    "G": "Diagnostics & setup",
}

_REQUEST_NEW_BLAST = BlastRadius(
    summary="Creates one Google Sheet and writes request + suppliers to the xsource store. Does not send or draft any email in P1.",
    reversible="Sheet can be deleted; store records can be removed by id.",
)

_REQUEST_OUTREACH_BLAST = BlastRadius(
    summary="Creates Gmail drafts for shortlisted suppliers and records draft/thread ids. It never sends email.",
    reversible="Drafts can be deleted from Gmail; outreach metadata can be removed from the request record.",
)

_INVOICE_CAPTURE_BLAST = BlastRadius(
    summary="Records one supplier invoice in the xsource store and links it to supplier/request history. It does not pay money.",
    reversible="Invoice and price-history rows can be corrected by operator edit.",
)

_REQUEST_LIST_BLAST = BlastRadius(
    summary="Writes nothing.",
    reversible="No write is performed.",
)

_BOOK_SEARCH_BLAST = BlastRadius(
    summary="Writes nothing.",
    reversible="No write is performed.",
)


def _status() -> dict:
    cfg = Config.from_env()
    suppliers: SyncedStore | None = None
    requests_: SyncedStore | None = None
    invoices: SyncedStore | None = None
    with contextlib.suppress(Exception):
        suppliers, requests_, invoices = build_stores(cfg)
    budget = build_budget(cfg, dt.date.today())
    return {
        "cfg": cfg,
        "suppliers": suppliers,
        "requests": requests_,
        "invoices": invoices,
        "budget": budget,
    }


def _store_online(*stores) -> bool:
    return bool(stores) and all(store is not None and not store.offline for store in stores)


def _quarantine_suffix(store) -> str:
    quarantined = getattr(store, "quarantined", 0)
    if not quarantined:
        return ""
    return f" · quarantined: {quarantined} corrupt line(s)"


def _readonly_preconditions(ctx: WizardContext) -> list[Precondition]:
    try:
        suppliers, requests_, invoices = build_stores(Config.from_env())
    except Exception:
        return [Precondition("Store loaded", False, "store unavailable")]
    stores = (suppliers, requests_, invoices)
    offline = any(getattr(store, "offline", False) for store in stores)
    return [
        Precondition(
            "Store loaded",
            True,
            "offline read-only cache" if offline else "GCS store available",
        )
    ]


def _preconditions(ctx: WizardContext) -> list[Precondition]:
    report = _status()
    cfg: Config = report["cfg"]
    suppliers = report["suppliers"]
    requests_ = report["requests"]
    invoices = report["invoices"]
    budget: Budget = report["budget"]
    sheets_token = os.environ.get("XSOURCE_SHEETS_TOKEN_PATH", "")
    return [
        Precondition(
            "Google Maps key",
            bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
            "present" if os.environ.get("GOOGLE_MAPS_API_KEY") else "missing",
        ),
        Precondition(
            "Anthropic key",
            bool(secret_from_env("ANTHROPIC_API_KEY")),
            "present" if secret_from_env("ANTHROPIC_API_KEY") else "missing",
        ),
        Precondition(
            "Sheets token",
            bool(sheets_token and Path(sheets_token).exists()),
            sheets_token or "missing",
        ),
        Precondition(
            "Store reachable",
            _store_online(suppliers, requests_, invoices),
            "GCS store available"
            if _store_online(suppliers, requests_, invoices)
            else "offline read-only cache",
        ),
        Precondition("Research budget", budget.allow_new_run(), budget.level()),
        Precondition("Home postcode", bool(cfg.home_postcode), cfg.home_postcode or "missing"),
    ]


def _outreach_preconditions(ctx: WizardContext) -> list[Precondition]:
    report = _status()
    suppliers = report["suppliers"]
    requests_ = report["requests"]
    invoices = report["invoices"]
    gmail_token = os.environ.get("XSOURCE_GMAIL_TOKEN_PATH", "")
    request_records = requests_.all() if requests_ is not None else []
    open_requests = [r for r in request_records if getattr(r, "status", "") == "open"]
    return [
        Precondition(
            "Anthropic key",
            bool(secret_from_env("ANTHROPIC_API_KEY")),
            "present" if secret_from_env("ANTHROPIC_API_KEY") else "missing",
        ),
        Precondition(
            "Gmail token",
            bool(gmail_token and Path(gmail_token).exists()),
            gmail_token or "missing",
        ),
        Precondition(
            "Store reachable",
            _store_online(suppliers, requests_, invoices),
            "GCS store available"
            if _store_online(suppliers, requests_, invoices)
            else "offline read-only cache",
        ),
        Precondition(
            "Open request",
            bool(open_requests),
            f"{len(open_requests)} open" if open_requests else "none",
        ),
    ]


def _invoice_preconditions(ctx: WizardContext) -> list[Precondition]:
    report = _status()
    suppliers = report["suppliers"]
    requests_ = report["requests"]
    invoices = report["invoices"]
    supplier_records = suppliers.all() if suppliers is not None else []
    return [
        Precondition(
            "Store reachable",
            _store_online(suppliers, requests_, invoices),
            "GCS store available"
            if _store_online(suppliers, requests_, invoices)
            else "offline read-only cache",
        ),
        Precondition(
            "Supplier available",
            bool(supplier_records),
            f"{len(supplier_records)} supplier(s)" if supplier_records else "none",
        ),
    ]


def _need_step(ctx: WizardContext, bag: dict) -> StepResult:
    raw_need = ctx.input_fn("Need: ").strip() if ctx.input_fn else ""
    if not raw_need:
        return StepResult(ok=False, message="No need entered.")
    return StepResult(
        ok=True,
        data={
            "raw_need": raw_need,
            "constraints": {
                "radius_miles": Config.from_env().default_radius_miles,
                "needed_by": None,
            },
        },
    )


def _is_retriable_anthropic_error(exc: Exception) -> bool:
    """Return True for availability errors that warrant trying the next model.

    Auth errors and bad-request errors are NOT retriable — they indicate a
    misconfiguration that a different model cannot fix.
    """
    err_type = type(exc).__name__
    # anthropic SDK raises these for availability/overload; everything else
    # (AuthenticationError, BadRequestError) is a hard failure.
    return err_type in {"InternalServerError", "OverloadedError", "APIStatusError"}


class _AnthropicStructuredGateway:
    def __init__(self, model_chain: list[str] | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=secret_from_env("ANTHROPIC_API_KEY"))
        if model_chain:
            self.model_chain = list(model_chain)
        else:
            single = os.environ.get("XSOURCE_RESEARCH_MODEL", "")
            chain_env = os.environ.get("XSOURCE_MODEL_CHAIN", "")
            if chain_env:
                self.model_chain = [m.strip() for m in chain_env.split(",") if m.strip()]
            elif single:
                self.model_chain = [single]
            else:
                self.model_chain = ["claude-sonnet-4-6"]

    def _call_model(self, model: str, messages, schema) -> dict:
        resp = self.client.messages.create(
            model=model,
            max_tokens=1200,
            tools=[
                {
                    "name": "report",
                    "description": "Return the structured result.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "report"},
            messages=messages,
        )
        for block in resp.content:
            block_any = cast(Any, block)
            if (
                getattr(block_any, "type", None) == "tool_use"
                and getattr(block_any, "name", None) == "report"
            ):
                return cast(dict, block_any.input)
        raise RuntimeError(f"model {model} returned no report tool call")

    def complete_structured(self, messages, schema, role: str = "research") -> dict:
        from xsource.obs import event as obs_event

        last_exc: Exception | None = None
        for i, model in enumerate(self.model_chain):
            try:
                return self._call_model(model, messages, schema)
            except Exception as exc:
                if not _is_retriable_anthropic_error(exc) or i == len(self.model_chain) - 1:
                    raise
                obs_event(
                    "gateway.model_fallback",
                    severity="warn",
                    role=role,
                    failed_model=model,
                    next_model=self.model_chain[i + 1],
                    error=str(exc),
                )
                last_exc = exc
        raise RuntimeError(f"{role} model chain exhausted") from last_exc


def _triage_step(ctx: WizardContext, bag: dict) -> StepResult:
    cfg = Config.from_env()
    triage = run_triage(
        bag["raw_need"], bag["constraints"], _AnthropicStructuredGateway(cfg.model_chain)
    )
    return StepResult(ok=True, data={"triage": triage.to_dict()})


def _research_step(ctx: WizardContext, bag: dict) -> StepResult:
    cfg = Config.from_env()
    suppliers, _requests, _invoices = build_stores(cfg)
    triage_dict = bag["triage"]
    triage = Triage(
        category=triage_dict["category"],
        search_terms=list(triage_dict["search_terms"]),
        also_try=list(triage_dict.get("also_try", [])),
        email_vars=dict(triage_dict["email_vars"]),
    )
    book_suppliers = find_matches(
        suppliers.all(),
        category=triage.category,
        tags=list(triage_dict.get("tags", [])),
    )
    book_matches = [
        Candidate(
            name=supplier.name,
            source="book",
            phone=supplier.phone,
            email=supplier.email,
            website=supplier.website,
            address=supplier.address,
            postcode=supplier.postcode,
            source_url=supplier.source_url,
            rating=(next(iter(supplier.rating.values()))[0] if supplier.rating else None),
            review_count=(next(iter(supplier.rating.values()))[1] if supplier.rating else None),
            rating_scale=5 if supplier.rating else None,
            extra={"supplier_id": supplier.id},
        )
        for supplier in book_suppliers
    ]
    fns = build_research_fns(cfg)
    result = run_research(
        triage=triage,
        book_matches=book_matches,
        places_fn=fns["places_fn"],
        directory_fn=fns["directory_fn"],
        price_fn=fns["price_fn"],
        ch_fn=fns["ch_fn"],
        caps=RunCaps(cfg.max_places_calls, cfg.max_web_searches),
        shortlist_n=cfg.shortlist_n,
    )
    return StepResult(ok=True, data={"result": result})


def _review_apply_step(ctx: WizardContext, bag: dict) -> StepResult:
    if not confirm_apply(ctx, prompt="Create request sheet?", equivalent_cli=None):  # type: ignore[arg-type]
        return StepResult(ok=False, message="Apply declined.")
    from google.oauth2.credentials import Credentials

    from xsource.walks.request_new import apply_request

    cfg = Config.from_env()
    suppliers, requests_, _invoices = build_stores(cfg)

    def create_sheet(title: str, values: list[list[str]]) -> tuple[str, str]:
        creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_SHEETS_TOKEN_PATH"])
        return SheetClient(creds).create_request_sheet(
            title, values, cfg.drive_folder_id, cfg.staff_share_group
        )

    request = apply_request(
        raw_need=bag["raw_need"],
        triage_dict=bag["triage"],
        constraints=bag["constraints"],
        result=bag["result"],
        suppliers=suppliers,
        requests=requests_,
        create_sheet_fn=create_sheet,
        now=dt.datetime.now(),
    )
    return StepResult(
        ok=True,
        data={
            "summary": f"Created {request.id}.",
            "result_links": [("Sheet", request.sheet_url or "")],
        },
    )


_request_new_handler = make_walk_handler(
    title="New procurement request",
    steps=[
        Step(label="Need", run=_need_step),
        Step(label="Triage", run=_triage_step),
        Step(label="Research", run=_research_step),
        Step(label="Review and apply", run=_review_apply_step),
    ],
    blast_radius=_REQUEST_NEW_BLAST,
    preconditions_fn=_preconditions,
    equivalent_cli="",  # cockpit-only walk; no CLI twin
    total=5,
)


def _outreach_select_step(ctx: WizardContext, bag: dict) -> StepResult:
    request_id = ctx.input_fn("Request id: ").strip() if ctx.input_fn else ""
    if not request_id:
        return StepResult(ok=False, message="No request id entered.")
    return StepResult(ok=True, data={"request_id": request_id})


def _outreach_apply_step(ctx: WizardContext, bag: dict) -> StepResult:
    if not confirm_apply(
        ctx,
        prompt="Create supplier outreach drafts?",
        equivalent_cli=None,  # type: ignore[arg-type]
    ):
        return StepResult(ok=False, message="Apply declined.")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    from xsource.outreach.client import SafeOutreachClient
    from xsource.outreach.drafts import create_request_drafts

    cfg = Config.from_env()
    suppliers, requests_, _invoices = build_stores(cfg)
    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_GMAIL_TOKEN_PATH"])
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    report = create_request_drafts(
        request_id=bag["request_id"],
        suppliers=suppliers,
        requests=requests_,
        draft_client=SafeOutreachClient(service),
        now=dt.datetime.now(dt.UTC),
        gateway=_AnthropicStructuredGateway(Config.from_env().model_chain),
    )
    return StepResult(
        ok=True,
        data={
            "summary": f"Created {report['drafted']} draft(s), skipped {report['skipped']}.",
        },
    )


_request_outreach_handler = make_walk_handler(
    title="Draft supplier outreach",
    steps=[
        Step(label="Request", run=_outreach_select_step),
        Step(label="Drafts", run=_outreach_apply_step),
    ],
    blast_radius=_REQUEST_OUTREACH_BLAST,
    preconditions_fn=_outreach_preconditions,
    equivalent_cli="",  # cockpit-only walk; no CLI twin
    total=2,
)


_TRIGGER_BLAST = BlastRadius(
    summary="Creates one Google Sheet and writes request + suppliers to the xsource store. Does not send or draft any email.",
    reversible="Sheet can be deleted; store records can be removed by id.",
)

_FOLLOWUP_BLAST = BlastRadius(
    summary="Creates one Gmail draft follow-up reply. It never sends email.",
    reversible="Draft can be deleted from Gmail; followup metadata can be removed from the request record.",
)

_REORDER_BLAST = BlastRadius(
    summary="Creates one Google Sheet and writes a reorder request + suppliers to the xsource store. Does not send or draft any email.",
    reversible="Sheet can be deleted; store records can be removed by id.",
)


def _trigger_step(ctx: WizardContext, bag: dict) -> StepResult:
    """Parse a trigger payload and let the operator amend the extracted need."""
    import json as _json

    focus = ctx.focus or ""
    payload: dict = {}
    if focus:
        with contextlib.suppress(Exception):
            payload = _json.loads(focus)
        if not payload:
            with contextlib.suppress(Exception):
                payload = _json.loads(Path(focus).read_text())

    if not payload:
        raw = ctx.input_fn("Trigger payload (JSON or file path): ").strip() if ctx.input_fn else ""
        if not raw:
            return StepResult(ok=False, message="No trigger payload provided.")
        with contextlib.suppress(Exception):
            payload = _json.loads(raw)
        if not payload:
            with contextlib.suppress(Exception):
                payload = _json.loads(Path(raw).read_text())
        if not payload:
            return StepResult(ok=False, message="Could not parse trigger payload.")

    from xsource.p4.triggers import parse_trigger

    parsed = parse_trigger(payload)
    if parsed is None:
        return StepResult(ok=False, message="Not a procurement trigger.")

    ctx.console.print(f"[dim]source:[/dim] {parsed.constraints.get('source', 'unknown')}")
    ctx.console.print(f"[dim]need:[/dim]   {parsed.raw_need}")
    amended = ctx.input_fn("Amend need (Enter to keep): ").strip() if ctx.input_fn else ""
    raw_need = amended if amended else parsed.raw_need

    cfg = Config.from_env()
    constraints = {
        **parsed.constraints,
        "radius_miles": cfg.default_radius_miles,
        "needed_by": None,
    }
    return StepResult(ok=True, data={"raw_need": raw_need, "constraints": constraints})


_request_trigger_handler = make_walk_handler(
    title="Trigger new request",
    steps=[
        Step(label="Trigger", run=_trigger_step),
        Step(label="Triage", run=_triage_step),
        Step(label="Research", run=_research_step),
        Step(label="Review and apply", run=_review_apply_step),
    ],
    blast_radius=_TRIGGER_BLAST,
    preconditions_fn=_preconditions,
    equivalent_cli="xsource request trigger",
    total=5,
)


def _followup_select_step(ctx: WizardContext, bag: dict) -> StepResult:
    """Select the request and supplier for a follow-up draft."""
    from xsource.p4.followup import build_followup_draft

    # Focus format: "request.followup:{request_id}:{supplier_id}" (pre-filled by CLI)
    _prefilled_request_id = ""
    _prefilled_supplier_id = ""
    focus = ctx.focus or ""
    if focus.startswith("request.followup:"):
        remainder = focus[len("request.followup:") :]
        if ":" in remainder:
            _prefilled_request_id, _prefilled_supplier_id = remainder.split(":", 1)
        else:
            _prefilled_request_id = remainder

    request_id = _prefilled_request_id or (
        ctx.input_fn("Request id: ").strip() if ctx.input_fn else ""
    )
    if not request_id:
        return StepResult(ok=False, message="No request id entered.")

    cfg = Config.from_env()
    suppliers, requests_, _invoices = build_stores(cfg)
    request = requests_.get(request_id)
    if request is None:
        return StepResult(ok=False, message=f"Unknown request {request_id}.")

    suppliers_by_id = {supplier.id: supplier for supplier in suppliers.all()}
    replied_entries = [
        entry for entry in request.shortlist if entry.reply and entry.supplier_id in suppliers_by_id
    ]
    if not replied_entries:
        return StepResult(ok=False, message=f"No replied shortlist entries for {request_id}.")

    ctx.console.print("[bold]Replied shortlist entries[/bold]")
    for entry in replied_entries:
        supplier = suppliers_by_id[entry.supplier_id]
        summary = entry.reply.get("summary") or "reply recorded"
        ctx.console.print(f"  {entry.rank}. {supplier.id} — {supplier.name}: {summary}")

    supplier_id = _prefilled_supplier_id or (
        ctx.input_fn("Supplier id: ").strip() if ctx.input_fn else ""
    )
    if not supplier_id:
        return StepResult(ok=False, message="No supplier id entered.")
    supplier = suppliers_by_id.get(supplier_id)
    if supplier is None:
        return StepResult(ok=False, message=f"Unknown supplier {supplier_id}.")
    if not any(entry.supplier_id == supplier_id for entry in replied_entries):
        return StepResult(
            ok=False,
            message=f"Supplier {supplier_id} has no recorded reply on {request_id}.",
        )

    draft = build_followup_draft(
        request,
        supplier,
        operator_name=cfg.operator_display_name,
    )
    ctx.console.print("[bold]Draft preview[/bold]")
    ctx.console.print(f"To: {draft['to']}")
    ctx.console.print(f"Subject: {draft['subject']}")
    ctx.console.print(draft["body"])
    return StepResult(
        ok=True,
        data={
            "request_id": request_id,
            "supplier_id": supplier_id,
            "request": request,
            "supplier": supplier,
        },
    )


def _invoice_details_step(ctx: WizardContext, bag: dict) -> StepResult:
    input_fn = ctx.input_fn
    if input_fn is None:
        return StepResult(ok=False, message="No input available.")
    supplier_id = input_fn("Supplier id: ").strip()
    amount_text = input_fn("Amount minor: ").strip()
    invoice_date = input_fn("Invoice date: ").strip()
    description = input_fn("Description: ").strip()
    if not supplier_id or not amount_text or not invoice_date or not description:
        return StepResult(ok=False, message="Missing invoice details.")
    try:
        amount_minor = int(amount_text)
    except ValueError:
        return StepResult(
            ok=False,
            message=f"Invalid amount {amount_text!r}: expected a whole number in minor units.",
        )
    if amount_minor <= 0:
        return StepResult(
            ok=False,
            message=f"Amount must be a positive integer in minor units, got {amount_minor}.",
        )
    try:
        validate_iso_date(invoice_date, "invoice_date")
    except ValueError as exc:
        return StepResult(ok=False, message=str(exc))
    request_id = input_fn("Request id (optional): ").strip()
    invoice_number = input_fn("Invoice number (optional): ").strip() or None
    due_date = input_fn("Due date (optional): ").strip() or None
    if due_date:
        try:
            validate_iso_date(due_date, "due_date")
        except ValueError as exc:
            return StepResult(ok=False, message=str(exc))
    return StepResult(
        ok=True,
        data={
            "supplier_id": supplier_id,
            "amount_minor": amount_minor,
            "invoice_date": invoice_date,
            "description": description,
            "request_id": request_id,
            "invoice_number": invoice_number,
            "due_date": due_date,
        },
    )


def _followup_apply_step(ctx: WizardContext, bag: dict) -> StepResult:
    """Preview and confirm the follow-up draft, then create it."""
    if not confirm_apply(
        ctx,
        prompt="Create follow-up draft?",
        equivalent_cli="xsource request followup",
    ):
        return StepResult(ok=False, message="Apply declined.")

    import os

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    from xsource.outreach.client import SafeOutreachClient
    from xsource.p4.followup import create_followup_draft

    cfg = Config.from_env()
    request = bag.get("request")
    supplier = bag.get("supplier")
    requests_ = None
    if request is None or supplier is None:
        suppliers, requests_, _invoices = build_stores(cfg)
        request = requests_.get(bag["request_id"])
        if request is None:
            return StepResult(ok=False, message=f"Unknown request {bag['request_id']}.")
        supplier = next((s for s in suppliers.all() if s.id == bag["supplier_id"]), None)
        if supplier is None:
            return StepResult(ok=False, message=f"Unknown supplier {bag['supplier_id']}.")
    else:
        _, requests_, _invoices = build_stores(cfg)

    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_GMAIL_TOKEN_PATH"])
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    result = create_followup_draft(
        request,
        supplier,
        draft_client=SafeOutreachClient(service),
        operator_name=cfg.operator_display_name,
        now=dt.datetime.now(dt.UTC),
    )
    requests_.upsert(request)
    return StepResult(
        ok=True,
        data={"summary": f"Created draft {result['draft_id']} for {supplier.name}."},
    )


_request_followup_handler = make_walk_handler(
    title="Draft follow-up reply",
    steps=[
        Step(label="Select", run=_followup_select_step),
        Step(label="Draft", run=_followup_apply_step),
    ],
    blast_radius=_FOLLOWUP_BLAST,
    preconditions_fn=_outreach_preconditions,
    equivalent_cli="xsource request followup",
    total=2,
)


def _invoice_apply_step(ctx: WizardContext, bag: dict) -> StepResult:
    if not confirm_apply(
        ctx,
        prompt="Capture invoice?",
        equivalent_cli="xsource invoice add",
    ):
        return StepResult(ok=False, message="Apply declined.")
    from xsource.invoices.capture import capture_invoice

    cfg = Config.from_env()
    suppliers, requests_, invoices = build_stores(cfg)
    try:
        report = capture_invoice(
            suppliers=suppliers,
            requests=requests_,
            invoices=invoices,
            request_id=bag.get("request_id") or "",
            supplier_id=bag["supplier_id"],
            amount_minor=bag["amount_minor"],
            invoice_number=bag.get("invoice_number"),
            invoice_date=bag["invoice_date"],
            due_date=bag.get("due_date"),
            description=bag["description"],
            source="manual",
        )
    except ValueError as exc:
        return StepResult(ok=False, message=str(exc))
    return StepResult(
        ok=True,
        data={"summary": f"Captured {report.invoice_id}.", "warnings": report.warnings},
    )


_invoice_capture_handler = make_walk_handler(
    title="Capture supplier invoice",
    steps=[
        Step(label="Invoice details", run=_invoice_details_step),
        Step(label="Review and apply", run=_invoice_apply_step),
    ],
    blast_radius=_INVOICE_CAPTURE_BLAST,
    preconditions_fn=_invoice_preconditions,
    equivalent_cli="xsource invoice add",
    total=2,
)


def _request_list_step(ctx: WizardContext, bag: dict) -> StepResult:
    _suppliers, requests_, _invoices = build_stores(Config.from_env())
    records = sorted(requests_.all(), key=lambda r: r.id)
    open_n = sum(1 for request in records if request.status == "open")
    total_n = len(records)
    rows = [format_request_row(request) for request in records]
    return StepResult(
        ok=True,
        data={
            "summary": f"{open_n} open · {total_n} total{_quarantine_suffix(requests_)}",
            "rows": rows,
        },
    )


def _book_search_term_step(ctx: WizardContext, bag: dict) -> StepResult:
    term = ctx.input_fn("Search term: ").strip() if ctx.input_fn else ""
    if not term:
        return StepResult(ok=False, message="No search term entered.")
    return StepResult(ok=True, data={"term": term})


def _book_search_results_step(ctx: WizardContext, bag: dict) -> StepResult:
    suppliers, _requests, _invoices = build_stores(Config.from_env())
    term = bag["term"]
    matches = search_suppliers(suppliers.all(), term)
    rows = [format_supplier_row(supplier) for supplier in matches]
    return StepResult(
        ok=True,
        data={
            "summary": f"{len(matches)} match(es) for '{term}'{_quarantine_suffix(suppliers)}",
            "rows": rows,
        },
    )


_request_list_handler = make_walk_handler(
    title="List procurement requests",
    steps=[Step(label="List", run=_request_list_step)],
    blast_radius=_REQUEST_LIST_BLAST,
    preconditions_fn=_readonly_preconditions,
    equivalent_cli=_CLI_REQUEST_LIST,
    total=2,
)


_book_search_handler = make_walk_handler(
    title="Search black book",
    steps=[
        Step(label="Term", run=_book_search_term_step),
        Step(label="Results", run=_book_search_results_step),
    ],
    blast_radius=_BOOK_SEARCH_BLAST,
    preconditions_fn=_readonly_preconditions,
    equivalent_cli=_CLI_BOOK_SEARCH,
    total=3,
)


def _reorder_proposal_step(ctx: WizardContext, bag: dict) -> StepResult:
    """Show the reorder proposal for a recurring supplier and capture the decision."""
    from xsource.p4.reorder import build_reorder_proposal

    focus = ctx.focus or ""
    supplier_id = focus.removeprefix("request.reorder:") if focus else ""
    if not supplier_id:
        supplier_id = ctx.input_fn("Supplier id: ").strip() if ctx.input_fn else ""
    if not supplier_id:
        return StepResult(ok=False, message="No supplier id provided.")

    cfg = Config.from_env()
    suppliers, requests_, _invoices = build_stores(cfg)
    supplier = next((s for s in suppliers.all() if s.id == supplier_id), None)
    if supplier is None:
        return StepResult(ok=False, message=f"Unknown supplier {supplier_id}.")

    proposal = build_reorder_proposal(supplier, requests_.all())
    ctx.console.print(f"[bold]Reorder proposal for {supplier.name}[/bold]")
    ctx.console.print(f"  Need:   {proposal.raw_need}")
    ctx.console.print(f"  Last done: {proposal.last_done or '—'}")
    ctx.console.print(f"  Due:    {proposal.due_at}")
    if proposal.budget_hint.get("sample_size", 0) > 0:
        ctx.console.print(
            f"  Budget hint: ~£{proposal.budget_hint['median']} "
            f"(n={proposal.budget_hint['sample_size']})"
        )
    choice = (
        ctx.input_fn("a) Reorder  b) Re-tender  c) Dismiss [a/b/c]: ").strip().lower()
        if ctx.input_fn
        else "c"
    )
    if choice not in ("a", "b"):
        return StepResult(ok=False, message="Dismissed.")

    reorder_constraints = {
        "radius_miles": cfg.default_radius_miles,
        "needed_by": None,
        "reorder_supplier_id": supplier_id,
        "budget_hint": proposal.budget_hint,
    }
    return StepResult(
        ok=True,
        data={
            "raw_need": proposal.raw_need,
            "constraints": reorder_constraints,
            "reorder_decision": "reorder" if choice == "a" else "retender",
            "reorder_supplier": supplier,
            "reorder_proposal": proposal,
        },
    )


def _reorder_research_step(ctx: WizardContext, bag: dict) -> StepResult:
    """For 'reorder': build a single-candidate result. For 're-tender': run full research."""
    from xsource.research.candidates import Candidate
    from xsource.research.pipeline import ResearchResult

    decision = bag.get("reorder_decision", "reorder")
    supplier = bag["reorder_supplier"]

    if decision == "reorder":
        candidate = Candidate(
            name=supplier.name,
            source="book",
            phone=supplier.phone,
            email=supplier.email,
            website=supplier.website,
            address=supplier.address,
            postcode=supplier.postcode,
            source_url=supplier.source_url,
            rating=None,
            review_count=None,
            rating_scale=None,
            extra={"supplier_id": supplier.id},
        )
        result = ResearchResult(shortlist=[candidate], indicative=None, stages={})
        proposal = bag["reorder_proposal"]
        triage = {
            "category": proposal.category,
            "search_terms": [],
            "also_try": [],
            "email_vars": {
                "job_summary": proposal.raw_need,
                "location_town": "",
            },
        }
        return StepResult(ok=True, data={"triage": triage, "result": result})

    # re-tender: run normal triage + research, then guarantee incumbent is in the shortlist
    triage_result = _triage_step(ctx, bag)
    if not triage_result.ok:
        return triage_result
    bag_with_triage = {**bag, **(triage_result.data or {})}

    research_result = _research_step(ctx, bag_with_triage)
    if not research_result.ok:
        return research_result

    # Inject incumbent into shortlist when category mismatch means find_matches missed them
    data = research_result.data or {}
    result = data["result"]
    if not any(c.extra.get("supplier_id") == supplier.id for c in result.shortlist):
        from xsource.research.pipeline import ResearchResult

        incumbent = Candidate(
            name=supplier.name,
            source="book",
            phone=supplier.phone,
            email=supplier.email,
            website=supplier.website,
            address=supplier.address,
            postcode=supplier.postcode,
            source_url=supplier.source_url,
            rating=None,
            review_count=None,
            rating_scale=None,
            extra={"supplier_id": supplier.id},
        )
        research_result = StepResult(
            ok=True,
            data={
                **data,
                "result": ResearchResult(
                    shortlist=[incumbent] + list(result.shortlist),
                    indicative=result.indicative,
                    stages=result.stages,
                    caps=result.caps,
                ),
            },
        )
    return research_result


_request_reorder_handler = make_walk_handler(
    title="Reorder recurring service",
    steps=[
        Step(label="Proposal", run=_reorder_proposal_step),
        Step(label="Research", run=_reorder_research_step),
        Step(label="Review and apply", run=_review_apply_step),
    ],
    blast_radius=_REORDER_BLAST,
    preconditions_fn=_preconditions,
    equivalent_cli="xsource request reorder",
    total=4,
)


def register_all() -> None:
    """Register xsource's cockpit capabilities."""
    register_capability(
        CapabilitySpec(
            key="request.new",
            shelf="A",
            title="New request",
            summary="Plain-English need to a pre-filled supplier shortlist Sheet.",
            equivalent_cli=None,  # type: ignore[arg-type]
            run=_request_new_handler,
            blast_radius=_REQUEST_NEW_BLAST,
        )
    )
    register_capability(
        CapabilitySpec(
            key="request.outreach",
            shelf="E",
            title="Draft outreach",
            summary="Create draft-only quote requests for suppliers on an open request.",
            equivalent_cli=None,  # type: ignore[arg-type]
            run=_request_outreach_handler,
            blast_radius=_REQUEST_OUTREACH_BLAST,
        )
    )
    register_capability(
        CapabilitySpec(
            key="request.trigger",
            shelf="A",
            title="Trigger new request",
            summary="Convert an approved email/chat trigger into request.new input.",
            equivalent_cli="xsource request trigger",
            run=_request_trigger_handler,
            blast_radius=_TRIGGER_BLAST,
        )
    )
    register_capability(
        CapabilitySpec(
            key="request.followup",
            shelf="E",
            title="Draft follow-up",
            summary="Create draft-only follow-up replies for supplier responses. It never sends email.",
            equivalent_cli="xsource request followup",
            run=_request_followup_handler,
            blast_radius=_FOLLOWUP_BLAST,
        )
    )
    register_capability(
        CapabilitySpec(
            key="request.reorder",
            shelf="A",
            title="Reorder recurring service",
            summary="Prefilled reorder from recurring supplier — review then apply. Does not send or draft any email in this step.",
            equivalent_cli="xsource request reorder",
            run=_request_reorder_handler,
            blast_radius=_REORDER_BLAST,
        )
    )
    register_capability(
        CapabilitySpec(
            key="invoice.capture",
            shelf="B",
            title="Capture invoice",
            summary="Record a supplier invoice for AP handoff; never pays money.",
            equivalent_cli="xsource invoice add",
            run=_invoice_capture_handler,
            blast_radius=_INVOICE_CAPTURE_BLAST,
        )
    )
    register_capability(
        CapabilitySpec(
            key="request.list",
            shelf="B",
            title="List requests",
            summary="List procurement requests from the store. Read-only.",
            equivalent_cli=_CLI_REQUEST_LIST,
            run=_request_list_handler,
            blast_radius=_REQUEST_LIST_BLAST,
            money_movement=False,
        )
    )
    register_capability(
        CapabilitySpec(
            key="book.search",
            shelf="C",
            title="Search black book",
            summary="Search saved suppliers by name, category, or tag. Read-only.",
            equivalent_cli=_CLI_BOOK_SEARCH,
            run=_book_search_handler,
            blast_radius=_BOOK_SEARCH_BLAST,
            money_movement=False,
        )
    )
    for key, shelf, title, summary, cli in (
        (
            "book.import",
            "C",
            "Import black book",
            "Seed the supplier store from CSV. Planned — not yet wired.",
            None,
        ),
        (
            "book.publish",
            "D",
            "Publish staff directory",
            "Regenerate the read-only staff supplier directory. Planned — not yet wired.",
            None,
        ),
        (
            "request.sync",
            "B",
            "Sync request Sheet",
            "Read human Sheet edits back into the request and black book. Read-only via CLI: xsource request sync.",
            "xsource request sync",
        ),
        (
            "watcher.status",
            "E",
            "Reply watcher",
            "Show watched threads, reply parsing, and heartbeat status. Read-only via CLI: xsource watcher status.",
            "xsource watcher status",
        ),
        (
            "partner.checkatrade",
            "D",
            "Checkatrade partner lead",
            "Prepare a signed partner lead request (build-only; posting requires an explicit gate). Build-only — post gate required.",
            None,
        ),
    ):
        register_capability(
            CapabilitySpec(
                key=key,
                shelf=shelf,
                title=title,
                summary=summary,
                equivalent_cli=cli,  # type: ignore[arg-type]
                run=None,
            )
        )
    register_capability(
        CapabilitySpec(
            key="doctor",
            shelf="G",
            title="Doctor",
            summary="Deep health check — auth, freshness, config. Live — press G to open.",
            equivalent_cli=None,  # type: ignore[arg-type]
            run=None,
        )
    )


def capture_state() -> CockpitState:
    """xsource's cockpit state."""
    report = _status()
    cfg: Config = report["cfg"]
    suppliers = report["suppliers"]
    requests_ = report["requests"]
    invoices = report["invoices"]
    budget: Budget = report["budget"]
    supplier_count = len(suppliers.all()) if suppliers is not None else 0
    request_records = requests_.all() if requests_ is not None else []
    invoice_records = invoices.all() if invoices is not None else []
    open_requests = [r for r in request_records if getattr(r, "status", "") == "open"]
    invoice_attention = [
        i for i in invoice_records if getattr(i, "status", "") in {"captured", "rejected"}
    ]
    budget_level = budget.level()

    needs = []
    now = dt.datetime.now(dt.UTC)
    for request in open_requests:
        try:
            created = dt.datetime.fromisoformat(request.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=dt.UTC)
            age_days = (now - created.astimezone(dt.UTC)).days
        except ValueError:
            age_days = 0
        if age_days >= cfg.chase_after_days:
            needs.append(
                NeedsItem(
                    title=f"Follow up {request.id}",
                    detail=f"{age_days}d open",
                    level="warn",
                    capability_key="request.list",
                )
            )
    if not needs:
        needs.append(
            NeedsItem(
                title="Ready for new request",
                detail="Use A to start supplier research.",
                level="ok",
                capability_key="request.new",
            )
        )

    store_online = _store_online(suppliers, requests_, invoices)

    pending_review = sum(
        1
        for request in open_requests
        for entry in request.watcher.get("possible_replies", [])
        if entry.get("status") == "needs_review"
    )

    pills: list[Pill] = [
        Pill(label="black book", status=str(supplier_count), detail="suppliers", level="ok"),
        Pill(
            label="open requests",
            status=str(len(open_requests)),
            detail="active",
            level="warn" if open_requests else "ok",
        ),
        Pill(
            label="invoices",
            status=str(len(invoice_attention)),
            detail="need attention",
            level="warn" if invoice_attention else "ok",
        ),
        Pill(
            label="research budget",
            status=budget_level,
            detail=f"£{budget.spent():.2f}",
            level="error" if budget_level == "blocked" else budget_level,
        ),
        Pill(
            label="store",
            status="online" if store_online else "offline",
            detail="GCS sync — new data is not persisting" if not store_online else "GCS sync",
            level="ok" if store_online else "error",
        ),
    ]
    if pending_review:
        pills.append(
            Pill(
                label="pending replies",
                status=str(pending_review),
                detail="needs review",
                level="warn",
            )
        )

    return CockpitState(
        tenant_name="Auto-Procurer",
        app_label=_APP_LABEL,
        date_label="",
        time_label="",
        pills=tuple(pills),
        needs=tuple(needs),
        shelves=_SHELVES,
        toolkit_label="toolkit",
    )


def build_walk_ctx(screen, read_key, *, focus: str | None = None) -> WizardContext:
    return WizardContext(
        state={},
        client=None,
        console=Console(),
        input_fn=make_clean_input_fn(),
        confirm_fn=default_confirm_fn(),
        present=screen.update,
        read_key=read_key,
        focus=focus,
    )


def activate_pill(pill, screen, read_key) -> None:
    screen.update(render.render_note("xsource", "No manual refresh is needed in P1."))
    read_key()


def doctor_build_report() -> object:
    return _status()


def doctor_build_probes(report: object) -> list[Probe]:
    cfg: Config = report["cfg"]  # type: ignore[index]
    suppliers = report["suppliers"]  # type: ignore[index]
    requests_ = report["requests"]  # type: ignore[index]
    invoices = report["invoices"]  # type: ignore[index]
    budget: Budget = report["budget"]  # type: ignore[index]
    sheets_token = os.environ.get("XSOURCE_SHEETS_TOKEN_PATH", "")
    store_online = _store_online(suppliers, requests_, invoices)
    return [
        Probe(
            name="Google Maps key",
            level="ok" if os.environ.get("GOOGLE_MAPS_API_KEY") else "error",
            detail="present" if os.environ.get("GOOGLE_MAPS_API_KEY") else "missing",
            fix=Fix("Set GOOGLE_MAPS_API_KEY", "export GOOGLE_MAPS_API_KEY=...", run=None),
        ),
        Probe(
            name="Anthropic key",
            level="ok" if os.environ.get("ANTHROPIC_API_KEY") else "error",
            detail="present" if os.environ.get("ANTHROPIC_API_KEY") else "missing",
            fix=Fix("Set ANTHROPIC_API_KEY", "export ANTHROPIC_API_KEY=...", run=None),
        ),
        Probe(
            name="Sheets token",
            level="ok" if sheets_token and Path(sheets_token).exists() else "error",
            detail=sheets_token or "missing",
            fix=Fix(
                "Set XSOURCE_SHEETS_TOKEN_PATH", "export XSOURCE_SHEETS_TOKEN_PATH=...", run=None
            ),
        ),
        Probe(
            name="Store",
            level="ok" if store_online else "error",
            detail="online"
            if store_online
            else (
                "offline — new data is not persisting"
                + (
                    f" ({get_offline_reason('state/xsource/suppliers.jsonl')})"
                    if get_offline_reason("state/xsource/suppliers.jsonl")
                    else ""
                )
            ),
            fix=None,
        ),
        Probe(
            name="Budget",
            level="error" if budget.level() == "blocked" else budget.level(),
            detail=f"{budget.level()} (£{budget.spent():.2f})",
            fix=None,
        ),
        Probe(
            name="Home postcode",
            level="ok" if cfg.home_postcode else "error",
            detail=cfg.home_postcode or "missing",
            fix=Fix("Set XSOURCE_HOME_POSTCODE", "export XSOURCE_HOME_POSTCODE=...", run=None),
        ),
    ]


def doctor_unconfigured_renderable() -> RenderableType:
    return render.render_note("Doctor", "Doctor could not build a report.")


def _on_open() -> None:
    register_all()
    with contextlib.suppress(Exception):
        signals_emit.scan_and_emit()


def _host(*, agent_mode: bool = False) -> shell.Host:
    return shell.Host(
        capture_state=capture_state,
        build_walk_ctx=build_walk_ctx,
        activate_pill=activate_pill,
        doctor_build_report=doctor_build_report,
        doctor_build_probes=doctor_build_probes,
        doctor_fixes_for=fixes_for,
        doctor_unconfigured_renderable=doctor_unconfigured_renderable,
        usage=usage,
        on_open=_on_open,
        app_label=_APP_LABEL,
        agent_mode=agent_mode,
    )


def run_cockpit(*, read_key=keys.read_key, screen=None, focus: str | None = None) -> None:
    host = _host()
    # When a focus is provided, derive the capability key from the "key:value" focus prefix.
    cap_key = focus.split(":")[0] if focus and ":" in focus else None
    if screen is not None:
        host.on_open()
        if cap_key:
            shell._open_capability(host, cap_key, screen, read_key, focus=focus)  # type: ignore[attr-defined]
        else:
            shell._home(host, screen, read_key)
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    console = Console()
    host.on_open()
    with console.screen() as scr:
        if cap_key:
            shell._open_capability(host, cap_key, scr, read_key, focus=focus)  # type: ignore[attr-defined]
        else:
            shell._home(host, scr, read_key)


def serve_agent(*, stdin=sys.stdin, stdout=sys.stdout, allow_apply: bool = False) -> None:
    from clonway_cockpit.agent import serve_agent_stdio

    serve_agent_stdio(_host(agent_mode=True), stdin=stdin, stdout=stdout, allow_apply=allow_apply)
