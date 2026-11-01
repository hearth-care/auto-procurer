from __future__ import annotations

import datetime as dt
from typing import Any

from xsource.sheet.client import SheetClient
from xsource.sheet.sync import apply_sheet_rows
from xsource.store.models import LogEntry, Request
from xsource.workbook import layout
from xsource.workbook.client import WorkbookClient
from xsource.workbook.contract import BOARD_COLUMNS
from xsource.workbook.readback import read_black_book_edits, read_job_edits
from xsource.workbook.stages import advance, record_price


def _log(log, request: Request | None, text: str, now: dt.datetime) -> None:
    log.upsert(
        LogEntry(
            id=log.next_id("l"),
            at=now.isoformat(),
            request_id=request.id if request else None,
            text=text,
        )
    )


def redraw_workbook(
    *, workbook_id: str, client: WorkbookClient, suppliers, requests, log, now: dt.datetime
) -> dict[str, Any]:
    all_suppliers = suppliers.all()
    by_id = {s.id: s for s in all_suppliers}
    names = {s.id: s.name for s in all_suppliers}
    before_suppliers = {s.id: s.to_dict() for s in all_suppliers}
    all_requests = requests.all()
    jobs = [r for r in all_requests if r.job_tab]
    warnings: list[str] = []

    for r in jobs:
        before = r.to_dict()
        rows = client.read_tab(workbook_id, r.job_tab or "")
        warnings.extend(read_job_edits(rows, r, by_id, on=now.date()))
        for line in advance(r, names=names):
            _log(log, r, line, now)
        if r.to_dict() != before:
            requests.upsert(r)

    warnings.extend(
        read_black_book_edits(client.read_tab(workbook_id, "Black book"), all_suppliers)
    )
    for s in all_suppliers:
        if s.to_dict() != before_suppliers[s.id]:
            suppliers.upsert(s)

    for r in jobs:
        client.write_tab(workbook_id, r.job_tab or "", layout.job_tab_rows(r, by_id))
    client.write_tab(workbook_id, "Board", [list(BOARD_COLUMNS), *layout.board_rows(all_requests)])
    client.write_tab(workbook_id, "Black book", layout.black_book_rows(all_suppliers, all_requests))
    client.write_tab(
        workbook_id, "Log", layout.log_rows(log.all(), {r.id: r for r in all_requests})
    )
    return {"jobs": len(jobs), "warnings": warnings}


def unmigrated(requests) -> list[Request]:
    return [r for r in requests.all() if r.status == "open" and r.sheet_id and not r.job_tab]


def migrate_open_requests(
    *,
    workbook_id: str,
    client: WorkbookClient,
    legacy_sheets: SheetClient,
    suppliers,
    requests,
    log,
    now: dt.datetime,
) -> list[str]:
    moved: list[str] = []
    for r in unmigrated(requests):
        rows = legacy_sheets.read_request_rows(r.sheet_id or "")
        apply_sheet_rows(r, rows, suppliers=suppliers, synced_at=now)
        for e in r.shortlist:
            amount = e.reply.get("quote_amount")
            if amount is not None and e.latest_price_minor is None:
                record_price(e, round(float(amount) * 100), on=now.date(), via="email")
            if r.status == "closed" and r.chosen_supplier_id:
                if e.supplier_id == r.chosen_supplier_id:
                    e.stage = "Booked"
                elif e.stage not in ("Declined", "Not chosen"):
                    e.stage = "Not chosen"

        category = r.triage.get("category") or " ".join(r.raw_need.split())[:40]
        r.title = r.title or category
        created = dt.datetime.fromisoformat(r.created_at).date()
        existing = client.tab_ids(workbook_id)
        r.job_tab = layout.job_tab_name(r.title, created, set(existing))
        r.job_tab_gid = client.ensure_tab(workbook_id, r.job_tab, index=len(existing))
        client.format_tab(workbook_id, r.job_tab_gid, "energy" if r.energy else "job")
        requests.upsert(r)
        _log(log, r, "Moved from its old Sheet", now)
        moved.append(f"{r.id} -> {r.job_tab}")
    return moved
