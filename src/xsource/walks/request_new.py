"""Domain logic for the request.new walk."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from xsource.research.candidates import Candidate
from xsource.research.pipeline import ResearchResult
from xsource.sheet.template import _SOURCE_LABEL
from xsource.store.models import LogEntry, Request, ShortlistEntry, Supplier
from xsource.workbook.layout import uk_phone
from xsource.workbook.stages import advance


def build_shortlist_rows(cands: list[Candidate]) -> list[dict]:
    return [
        {"candidate": candidate, "mode": "email" if candidate.email else "call"}
        for candidate in cands
    ]


def _upsert_supplier(suppliers, candidate: Candidate, today: str) -> str:
    for supplier in suppliers.all():
        if supplier.name.lower() == candidate.name.lower():
            return supplier.id
    supplier_id = suppliers.next_id("s")
    suppliers.upsert(
        Supplier(
            id=supplier_id,
            name=candidate.name,
            phone=candidate.phone,
            email=candidate.email,
            website=candidate.website,
            address=candidate.address,
            place_id=candidate.place_id,
            rating={candidate.source: [candidate.rating, candidate.review_count]}
            if candidate.rating is not None
            else {},
            source=candidate.source,
            source_url=candidate.source_url,
            companies_house=(candidate.extra or {}).get("companies_house"),
            first_seen=today,
        )
    )
    return supplier_id


def shortlist_preview_rows(cands: list[Candidate]) -> list[str]:
    rows = []
    for rank, candidate in enumerate(cands, start=1):
        miles = (candidate.extra or {}).get("miles")
        rows.append(
            f"{rank:>2}  {candidate.name}  {f'{miles:.1f} mi' if miles is not None else '—'}  "
            f"{uk_phone(candidate.phone) or '—'}  "
            f"{_SOURCE_LABEL.get(candidate.source, candidate.source)}"
        )
    return rows


def _job_title(raw_need: str, triage_dict: dict) -> str:
    return (
        triage_dict.get("short_label")
        or triage_dict.get("category")
        or " ".join(raw_need.split())[:40]
    )


def apply_request(
    raw_need: str,
    triage_dict: dict,
    constraints: dict,
    result: ResearchResult,
    suppliers,
    requests,
    add_job_tab_fn: Callable[[Request], tuple[str, int]],
    log,
    now: dt.datetime,
    excluded_names: set[str] | None = None,
) -> Request:
    excluded = excluded_names or set()
    keep = [candidate for candidate in result.shortlist if candidate.name not in excluded]

    today = now.strftime("%Y-%m-%d")
    request_id = requests.next_id("r")
    entries = []
    names = {}
    for rank, candidate in enumerate(keep, start=1):
        supplier_id = _upsert_supplier(suppliers, candidate, today)
        names[supplier_id] = candidate.name
        entries.append(
            ShortlistEntry(
                supplier_id=supplier_id,
                rank=rank,
                miles=(candidate.extra or {}).get("miles"),
            )
        )
    request = Request(
        id=request_id,
        created_at=now.isoformat(),
        raw_need=raw_need,
        triage=triage_dict,
        constraints=constraints,
        status="open",
        indicative_range=result.indicative,
        shortlist=entries,
        title=_job_title(raw_need, triage_dict),
        energy=triage_dict.get("category") == "energy",
    )
    advance(request, names=names)
    request.job_tab, request.job_tab_gid = add_job_tab_fn(request)
    requests.upsert(request)
    log.upsert(
        LogEntry(
            id=log.next_id("l"),
            at=now.isoformat(),
            request_id=request.id,
            text=f"Job started with {len(entries)} firms on the shortlist",
        )
    )
    return request
