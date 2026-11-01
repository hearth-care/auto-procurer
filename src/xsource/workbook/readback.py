from __future__ import annotations

import datetime as dt
import re

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.workbook import contract
from xsource.workbook.layout import uk_phone
from xsource.workbook.stages import record_price

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d/%m/%y")


def parse_money_minor(text: str) -> int | None:
    cleaned = re.sub(r"[£,\s]", "", text or "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    whole, _, pence = cleaned.partition(".")
    return int(whole) * 100 + int(pence.ljust(2, "0") or 0)


def _phone(cell: str) -> str:
    return uk_phone(cell.strip().lstrip("'").strip())


def _parse_date(text: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _cells(row: list[str], index: dict[str, int]) -> dict[str, str]:
    return {name: (row[i].strip() if i < len(row) else "") for name, i in index.items()}


def read_job_edits(
    rows: list[list[str]],
    request: Request,
    suppliers: dict[str, Supplier],
    *,
    on: dt.date,
) -> list[str]:
    if not rows:
        return []
    tab = request.job_tab or request.title or request.id
    index = {name: i for i, name in enumerate(rows[0])}
    if "Firm" not in index:
        return [f"{tab}: no Firm column, edits not read"]
    editable = contract.ENERGY_JOB_HAND_EDITABLE if request.energy else contract.JOB_HAND_EDITABLE
    wanted = {n: index[n] for n in ("Firm", *editable) if n in index}
    entries: dict[str, tuple[ShortlistEntry, Supplier]] = {}
    for e in request.shortlist:
        s = suppliers.get(e.supplier_id)
        if s is not None:
            entries[s.name.casefold()] = (e, s)

    warnings: list[str] = []
    for raw in rows[1:]:
        cell = _cells(raw, wanted)
        firm = cell["Firm"]
        if not firm:
            continue
        found = entries.get(firm.casefold())
        if found is None:
            warnings.append(f"{tab}: no firm called '{firm}' on this job")
            continue
        entry, supplier = found

        if cell.get("Contact") and cell["Contact"] != entry.contact_name:
            entry.contact_name = cell["Contact"]
        if cell.get("Phone"):
            phone = _phone(cell["Phone"])
            if phone != uk_phone(supplier.phone):
                supplier.phone = phone
        if cell.get("Email") and cell["Email"] != supplier.email:
            supplier.email = cell["Email"]
        if cell.get("Notes") and cell["Notes"] != entry.notes:
            entry.notes = cell["Notes"]

        original_stage = entry.stage
        via = entry.last_contact.get("via") or "email"
        first = parse_money_minor(cell.get("First price", ""))
        latest = parse_money_minor(cell.get("Latest price", ""))
        if request.energy:
            for header, key in (
                ("Term", "term"),
                ("Unit rate", "unit_rate"),
                ("Standing charge", "standing_charge"),
            ):
                if cell.get(header) and cell[header] != str(entry.energy_quote.get(key, "")):
                    entry.energy_quote[key] = cell[header]
            latest = parse_money_minor(cell.get("Est. yearly cost", ""))
        if first is not None and first != entry.first_price_minor:
            entry.first_price_minor = first
        if latest is not None and latest != entry.latest_price_minor:
            record_price(entry, latest, on=on, via=via)

        stage = cell.get("Stage", "")
        if stage and stage != original_stage:
            if stage in contract.FIRM_STAGES:
                entry.stage = stage
            else:
                warnings.append(f"{tab}: '{stage}' is not a stage, ignored for {firm}")
    return warnings


def read_black_book_edits(rows: list[list[str]], suppliers: list[Supplier]) -> list[str]:
    if not rows:
        return []
    index = {name: i for i, name in enumerate(rows[0])}
    if "Firm" not in index:
        return ["Black book: no Firm column, edits not read"]
    wanted = {n: index[n] for n in ("Firm", *contract.BLACK_BOOK_HAND_EDITABLE) if n in index}
    by_name = {s.name.casefold(): s for s in suppliers}

    warnings: list[str] = []
    for raw in rows[1:]:
        cell = _cells(raw, wanted)
        firm = cell["Firm"]
        if not firm:
            continue
        supplier = by_name.get(firm.casefold())
        if supplier is None:
            warnings.append(f"Black book: no firm called '{firm}'")
            continue
        if cell.get("Contact") and cell["Contact"] != supplier.contact_name:
            supplier.contact_name = cell["Contact"]
        if cell.get("Phone"):
            phone = _phone(cell["Phone"])
            if phone != uk_phone(supplier.phone):
                supplier.phone = phone
        if cell.get("Email") and cell["Email"] != supplier.email:
            supplier.email = cell["Email"]
        if cell.get("Contract ends"):
            day = _parse_date(cell["Contract ends"])
            if day is None:
                warnings.append(
                    f"Black book: '{cell['Contract ends']}' is not a date, ignored for {firm}"
                )
            else:
                supplier.contract_ends = day
        if cell.get("Notice to give"):
            digits = cell["Notice to give"]
            if digits.isdigit():
                supplier.notice_days = int(digits)
            else:
                warnings.append(
                    f"Black book: '{digits}' is not a number of days, ignored for {firm}"
                )
    return warnings
