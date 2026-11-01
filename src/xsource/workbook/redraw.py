from __future__ import annotations

import datetime as dt
import json
from typing import Any

from xsource.sheet.client import SheetClient
from xsource.sheet.sync import apply_sheet_rows
from xsource.store.files import SyncedFile
from xsource.store.models import LogEntry, Request
from xsource.workbook import layout
from xsource.workbook.client import TabMissing, WorkbookClient
from xsource.workbook.contract import BOARD_COLUMNS
from xsource.workbook.readback import (
    TabSnapshot,
    black_book_key,
    job_key,
    read_black_book_edits,
    read_job_edits,
    snapshot_rows,
)
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


def _load_drawn(drawn_file: SyncedFile) -> dict[str, TabSnapshot]:
    drawn_file.hydrate()
    if not drawn_file.path.exists():
        return {}
    return json.loads(drawn_file.path.read_text())


def _save_drawn(drawn_file: SyncedFile, drawn: dict[str, TabSnapshot]) -> None:
    drawn_file.path.write_text(json.dumps(drawn, ensure_ascii=False))
    drawn_file.upload()


def redraw_workbook(
    *,
    workbook_id: str,
    client: WorkbookClient,
    suppliers,
    requests,
    log,
    drawn_file: SyncedFile,
    now: dt.datetime,
) -> dict[str, Any]:
    all_suppliers = suppliers.all()
    by_id = {s.id: s for s in all_suppliers}
    names = {s.id: s.name for s in all_suppliers}
    before_suppliers = {s.id: s.to_dict() for s in all_suppliers}
    all_requests = requests.all()
    drawn = _load_drawn(drawn_file)
    jobs: list[Request] = []
    warnings: list[str] = []

    for r in (r for r in all_requests if r.job_tab):
        tab = r.job_tab or ""
        before = r.to_dict()
        try:
            rows = client.read_tab(workbook_id, tab)
        except TabMissing:
            warnings.append(f"{tab}: tab missing, not redrawn")
            continue
        jobs.append(r)
        warnings.extend(read_job_edits(rows, r, by_id, on=now.date(), drawn=drawn.get(tab)))
        for line in advance(r, names=names):
            _log(log, r, line, now)
        if r.to_dict() != before:
            requests.upsert(r)

    warnings.extend(
        read_black_book_edits(
            client.read_tab(workbook_id, "Black book"), all_suppliers, drawn=drawn.get("Black book")
        )
    )
    for s in all_suppliers:
        if s.to_dict() != before_suppliers[s.id]:
            suppliers.upsert(s)

    # The snapshot is saved after each tab so a failed later write cannot leave an earlier,
    # already-redrawn tab compared against a stale snapshot (which would read as an edit).
    for r in jobs:
        tab = r.job_tab or ""
        rows = layout.job_tab_rows(r, by_id)
        client.write_tab(workbook_id, tab, rows)
        drawn[tab] = snapshot_rows(rows, job_key)
        _save_drawn(drawn_file, drawn)
    client.write_tab(workbook_id, "Board", [list(BOARD_COLUMNS), *layout.board_rows(all_requests)])
    rows = layout.black_book_rows(all_suppliers, all_requests)
    client.write_tab(workbook_id, "Black book", rows)
    drawn["Black book"] = snapshot_rows(rows, black_book_key)
    _save_drawn(drawn_file, drawn)
    client.write_tab(
        workbook_id, "Log", layout.log_rows(log.all(), {r.id: r for r in all_requests})
    )
    return {"jobs": len(jobs), "warnings": warnings}


def forget_drawn(drawn_file: SyncedFile, tab: str) -> None:
    # A reused tab name must not inherit a deleted tab's last-drawn cells.
    drawn = _load_drawn(drawn_file)
    if drawn.pop(tab, None) is not None:
        _save_drawn(drawn_file, drawn)


def add_job_tab(
    *,
    workbook_id: str,
    client: WorkbookClient,
    request: Request,
    requests,
    index: int | None = None,
) -> tuple[str, int]:
    created = layout.london_date(request.created_at)
    existing = client.tab_ids(workbook_id)
    # A tab deleted by hand leaves its job pointing at the name (it is skipped, not
    # recreated), so a new job taking that name would share a tab with it.
    taken = set(existing) | {r.job_tab for r in requests.all() if r.job_tab}
    name = layout.job_tab_name(request.title or "", created, taken)
    gid = client.ensure_tab(workbook_id, name, index=len(existing) if index is None else index)
    # format_tab is not idempotent; the name is unique, so the tab is always new here.
    client.format_tab(workbook_id, gid, "energy" if request.energy else "job")
    return name, gid


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
    drawn_file: SyncedFile,
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
        r.job_tab, r.job_tab_gid = add_job_tab(
            workbook_id=workbook_id, client=client, request=r, requests=requests
        )
        requests.upsert(r)
        forget_drawn(drawn_file, r.job_tab)
        _log(log, r, "Moved from its old Sheet", now)
        moved.append(f"{r.id} -> {r.job_tab}")
    return moved
