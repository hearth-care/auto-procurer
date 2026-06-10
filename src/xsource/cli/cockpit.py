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

from xsource.book.search import find_matches
from xsource.budget import Budget
from xsource.config import Config
from xsource.research.candidates import Candidate
from xsource.research.pipeline import RunCaps, run_research
from xsource.research.triage import Triage, run_triage
from xsource.sheet.client import SheetClient
from xsource.signals import emit as signals_emit
from xsource.store.remote import SyncedStore
from xsource.wiring import build_budget, build_research_fns, build_stores

_APP_LABEL = "xsource"

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


def _status() -> dict:
    cfg = Config.from_env()
    suppliers: SyncedStore | None = None
    requests_: SyncedStore | None = None
    with contextlib.suppress(Exception):
        suppliers, requests_ = build_stores(cfg)
    budget = build_budget(cfg, dt.date.today())
    return {"cfg": cfg, "suppliers": suppliers, "requests": requests_, "budget": budget}


def _store_online(suppliers, requests_) -> bool:
    return (
        suppliers is not None
        and requests_ is not None
        and not suppliers.offline
        and not requests_.offline
    )


def _preconditions(ctx: WizardContext) -> list[Precondition]:
    report = _status()
    cfg: Config = report["cfg"]
    suppliers = report["suppliers"]
    requests_ = report["requests"]
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
            bool(os.environ.get("ANTHROPIC_API_KEY")),
            "present" if os.environ.get("ANTHROPIC_API_KEY") else "missing",
        ),
        Precondition(
            "Sheets token",
            bool(sheets_token and Path(sheets_token).exists()),
            sheets_token or "missing",
        ),
        Precondition(
            "Store reachable",
            _store_online(suppliers, requests_),
            "GCS store available"
            if _store_online(suppliers, requests_)
            else "offline read-only cache",
        ),
        Precondition("Research budget", budget.allow_new_run(), budget.level()),
        Precondition("Home postcode", bool(cfg.home_postcode), cfg.home_postcode or "missing"),
    ]


def _outreach_preconditions(ctx: WizardContext) -> list[Precondition]:
    report = _status()
    suppliers = report["suppliers"]
    requests_ = report["requests"]
    gmail_token = os.environ.get("XSOURCE_GMAIL_TOKEN_PATH", "")
    request_records = requests_.all() if requests_ is not None else []
    open_requests = [r for r in request_records if getattr(r, "status", "") == "open"]
    return [
        Precondition(
            "Anthropic key",
            bool(os.environ.get("ANTHROPIC_API_KEY")),
            "present" if os.environ.get("ANTHROPIC_API_KEY") else "missing",
        ),
        Precondition(
            "Gmail token",
            bool(gmail_token and Path(gmail_token).exists()),
            gmail_token or "missing",
        ),
        Precondition(
            "Store reachable",
            _store_online(suppliers, requests_),
            "GCS store available"
            if _store_online(suppliers, requests_)
            else "offline read-only cache",
        ),
        Precondition(
            "Open request",
            bool(open_requests),
            f"{len(open_requests)} open" if open_requests else "none",
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


class _AnthropicStructuredGateway:
    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = os.environ.get("XSOURCE_RESEARCH_MODEL", "claude-sonnet-4-6")

    def complete_structured(self, messages, schema, role: str = "research") -> dict:
        resp = self.client.messages.create(
            model=self.model,
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
        raise RuntimeError(f"{role} model returned no report tool call")


def _triage_step(ctx: WizardContext, bag: dict) -> StepResult:
    triage = run_triage(bag["raw_need"], bag["constraints"], _AnthropicStructuredGateway())
    return StepResult(ok=True, data={"triage": triage.to_dict()})


def _research_step(ctx: WizardContext, bag: dict) -> StepResult:
    cfg = Config.from_env()
    suppliers, _requests = build_stores(cfg)
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
    if not confirm_apply(ctx, prompt="Create request sheet?", equivalent_cli="xsource request new"):
        return StepResult(ok=False, message="Apply declined.")
    from google.oauth2.credentials import Credentials

    from xsource.walks.request_new import apply_request

    cfg = Config.from_env()
    suppliers, requests_ = build_stores(cfg)

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
    equivalent_cli="xsource request new",
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
        equivalent_cli="xsource request outreach",
    ):
        return StepResult(ok=False, message="Apply declined.")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    from xsource.outreach.client import SafeOutreachClient
    from xsource.outreach.drafts import create_request_drafts

    cfg = Config.from_env()
    suppliers, requests_ = build_stores(cfg)
    creds = Credentials.from_authorized_user_file(os.environ["XSOURCE_GMAIL_TOKEN_PATH"])
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    report = create_request_drafts(
        request_id=bag["request_id"],
        suppliers=suppliers,
        requests=requests_,
        draft_client=SafeOutreachClient(service),
        now=dt.datetime.now(dt.UTC),
        gateway=_AnthropicStructuredGateway(),
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
    equivalent_cli="xsource request outreach",
    total=2,
)


def register_all() -> None:
    """Register xsource's cockpit capabilities."""
    register_capability(
        CapabilitySpec(
            key="request.new",
            shelf="A",
            title="New request",
            summary="Plain-English need to a pre-filled supplier shortlist Sheet.",
            equivalent_cli="xsource request new",
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
            equivalent_cli="xsource request outreach",
            run=_request_outreach_handler,
            blast_radius=_REQUEST_OUTREACH_BLAST,
        )
    )
    for key, shelf, title, summary, cli in (
        (
            "request.list",
            "B",
            "List requests",
            "Show open and recent procurement requests.",
            "xsource request list",
        ),
        (
            "book.search",
            "C",
            "Search black book",
            "Search saved suppliers by name, category, or tag.",
            "xsource book search",
        ),
        (
            "book.import",
            "C",
            "Import black book",
            "Seed the supplier store from CSV.",
            "xsource book import",
        ),
        (
            "book.publish",
            "D",
            "Publish staff directory",
            "Regenerate the read-only staff supplier directory.",
            "xsource book publish",
        ),
        (
            "request.sync",
            "B",
            "Sync request Sheet",
            "Read human Sheet edits back into the request and black book.",
            "xsource request sync",
        ),
        (
            "watcher.status",
            "E",
            "Reply watcher",
            "Show watched threads, reply parsing, and heartbeat status.",
            "xsource watcher status",
        ),
        (
            "request.trigger",
            "A",
            "Trigger new request",
            "Convert an approved email/chat trigger into request.new input.",
            "xsource request trigger",
        ),
        (
            "request.followup",
            "E",
            "Draft follow-up",
            "Create draft-only follow-up replies for supplier responses.",
            "xsource request followup",
        ),
        (
            "partner.checkatrade",
            "D",
            "Checkatrade partner lead",
            "Prepare a signed partner lead request; posting requires an explicit gate.",
            "xsource partner checkatrade",
        ),
    ):
        register_capability(
            CapabilitySpec(
                key=key,
                shelf=shelf,
                title=title,
                summary=summary,
                equivalent_cli=cli,
                run=None,
            )
        )
    register_capability(
        CapabilitySpec(
            key="doctor",
            shelf="G",
            title="Doctor",
            summary="Deep health check - auth, freshness, config.",
            equivalent_cli="xsource doctor",
            run=None,
        )
    )


def capture_state() -> CockpitState:
    """xsource's cockpit state."""
    report = _status()
    cfg: Config = report["cfg"]
    suppliers = report["suppliers"]
    requests_ = report["requests"]
    budget: Budget = report["budget"]
    supplier_count = len(suppliers.all()) if suppliers is not None else 0
    request_records = requests_.all() if requests_ is not None else []
    open_requests = [r for r in request_records if getattr(r, "status", "") == "open"]
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

    store_online = _store_online(suppliers, requests_)
    return CockpitState(
        tenant_name="Auto-Procurer",
        app_label=_APP_LABEL,
        date_label="",
        time_label="",
        pills=(
            Pill(label="black book", status=str(supplier_count), detail="suppliers", level="ok"),
            Pill(
                label="open requests",
                status=str(len(open_requests)),
                detail="active",
                level="warn" if open_requests else "ok",
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
                detail="GCS sync",
                level="ok" if store_online else "warn",
            ),
        ),
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
    budget: Budget = report["budget"]  # type: ignore[index]
    sheets_token = os.environ.get("XSOURCE_SHEETS_TOKEN_PATH", "")
    store_online = _store_online(suppliers, requests_)
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
            level="ok" if store_online else "warn",
            detail="online" if store_online else "offline read-only cache",
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
    return render.render_note("xsource doctor", "Doctor could not build a report.")


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


def run_cockpit(*, read_key=keys.read_key, screen=None) -> None:
    host = _host()
    if screen is not None:
        host.on_open()
        shell._home(host, screen, read_key)
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    console = Console()
    host.on_open()
    with console.screen() as scr:
        shell._home(host, scr, read_key)


def serve_agent(*, stdin=sys.stdin, stdout=sys.stdout, allow_apply: bool = False) -> None:
    from clonway_cockpit.agent import serve_agent_stdio

    serve_agent_stdio(_host(agent_mode=True), stdin=stdin, stdout=stdout, allow_apply=allow_apply)
