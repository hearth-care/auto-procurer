"""Domain logic for the request.new walk."""

from __future__ import annotations

import datetime as dt

from xsource.research.candidates import Candidate
from xsource.research.pipeline import ResearchResult
from xsource.sheet.template import build_values
from xsource.store.models import Request, ShortlistEntry, Supplier


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


def apply_request(
    raw_need: str,
    triage_dict: dict,
    constraints: dict,
    result: ResearchResult,
    suppliers,
    requests,
    create_sheet_fn,
    now: dt.datetime,
    excluded_names: set[str] | None = None,
) -> Request:
    excluded = excluded_names or set()
    keep = [candidate for candidate in result.shortlist if candidate.name not in excluded]
    short_need = raw_need.strip().split(".")[0][:40]
    title = f"Procurement - {short_need} - {now.strftime('%d %b')}"
    job_line = f"{short_need} - needed by {constraints.get('needed_by') or '-'}"
    values = build_values(
        request_id="(pending)",
        job_line=job_line,
        indicative=result.indicative,
        rows=keep,
        indicatives=[None] * len(keep),
        now_label=now.strftime("%d %b %H:%M"),
    )
    sheet_id, sheet_url = create_sheet_fn(title, values)

    today = now.strftime("%Y-%m-%d")
    request_id = requests.next_id("r")
    entries = []
    for rank, candidate in enumerate(keep, start=1):
        supplier_id = _upsert_supplier(suppliers, candidate, today)
        entries.append(ShortlistEntry(supplier_id=supplier_id, rank=rank))
    request = Request(
        id=request_id,
        created_at=now.isoformat(),
        raw_need=raw_need,
        triage=triage_dict,
        constraints=constraints,
        status="open",
        sheet_id=sheet_id,
        sheet_url=sheet_url,
        indicative_range=result.indicative,
        shortlist=entries,
    )
    requests.upsert(request)
    return request
