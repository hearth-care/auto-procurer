from __future__ import annotations

import datetime as dt
import re

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.workbook import contract
from xsource.workbook.layout import uk_phone
from xsource.workbook.stages import record_price

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d/%m/%y")

# firm (Black book: "kind|firm") -> header -> the string last drawn into that cell.
TabSnapshot = dict[str, dict[str, str]]


def parse_money_minor(text: str) -> int | None:
    cleaned = re.sub(r"[£,\s]", "", text or "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    whole, _, pence = cleaned.partition(".")
    return int(whole) * 100 + int(pence.ljust(2, "0") or 0)


def _plain(text: str) -> str:
    return (text or "").strip().lstrip("'").strip()


def _phone(cell: str) -> str:
    return uk_phone(_plain(cell))


def _parse_date(text: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _number(text: str) -> float | None:
    try:
        return float(re.sub(r"[£,\s]", "", text))
    except ValueError:
        return None


def _same(cell: str, drawn: str) -> bool:
    a, b = _plain(cell), _plain(drawn)
    if a == b:
        return True
    # Sheets reformats what we draw ("24.5" comes back "24.50"), so numbers compare by value.
    na, nb = _number(a), _number(b)
    return na is not None and na == nb


def _edited(cell: str, drawn: dict[str, str], header: str) -> bool:
    return bool(_plain(cell)) and not _same(cell, drawn.get(header, ""))


def _cells(row: list[str], index: dict[str, int]) -> dict[str, str]:
    return {name: (row[i].strip() if i < len(row) else "") for name, i in index.items()}


def snapshot_rows(rows: list[list[str]], key) -> TabSnapshot:
    if not rows:
        return {}
    header = rows[0]
    out: TabSnapshot = {}
    for raw in rows[1:]:
        cells = {h: (raw[i] if i < len(raw) else "") for i, h in enumerate(header)}
        out[key(cells)] = cells
    return out


# Keys are built from the drawn rows, where free text carries the ' escape, and looked up
# with what Sheets shows, where it does not; both sides go through _plain.
def job_key(cells: dict[str, str]) -> str:
    return _plain(cells["Firm"]).casefold()


def black_book_key(cells: dict[str, str]) -> str:
    return f"{_plain(cells['Kind of job'])}|{_plain(cells['Firm'])}".casefold()


def read_job_edits(
    rows: list[list[str]],
    request: Request,
    suppliers: dict[str, Supplier],
    *,
    on: dt.date,
    drawn: TabSnapshot | None,
) -> list[str]:
    if not rows or not drawn:
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
        firm = _plain(cell["Firm"])
        if not firm:
            continue
        found = entries.get(firm.casefold())
        if found is None:
            warnings.append(f"{tab}: no firm called '{firm}' on this job")
            continue
        entry, supplier = found
        # A row with no snapshot is a firm typed over another: comparing it with nothing
        # would read every cell as an edit and copy the old firm's details onto this one.
        was = drawn.get(job_key(cell))
        if was is None:
            warnings.append(f"{tab}: '{firm}' was not drawn here; edits ignored")
            continue

        def changed(header: str, cell=cell, was=was) -> bool:
            return _edited(cell.get(header, ""), was, header)

        if changed("Contact"):
            entry.contact_name = cell["Contact"]
        if changed("Phone"):
            supplier.phone = _phone(cell["Phone"])
        if changed("Email"):
            supplier.email = cell["Email"]
        if changed("Notes"):
            entry.notes = cell["Notes"]

        original_stage = entry.stage
        via = entry.last_contact.get("via") or "email"
        if request.energy:
            for header, key in (
                ("Term", "term"),
                ("Unit rate", "unit_rate"),
                ("Standing charge", "standing_charge"),
            ):
                if changed(header):
                    entry.energy_quote[key] = cell[header]
            latest_header = "Est. yearly cost"
        else:
            latest_header = "Latest price"
            if changed("First price") and (m := parse_money_minor(cell["First price"])) is not None:
                entry.first_price_minor = m
        if changed(latest_header) and (m := parse_money_minor(cell[latest_header])) is not None:
            record_price(entry, m, on=on, via=via)

        if changed("Stage"):
            if cell["Stage"] in contract.FIRM_STAGES:
                if cell["Stage"] != original_stage:
                    entry.stage = cell["Stage"]
            else:
                warnings.append(f"{tab}: '{cell['Stage']}' is not a stage, ignored for {firm}")
    return warnings


def read_black_book_edits(
    rows: list[list[str]], suppliers: list[Supplier], *, drawn: TabSnapshot | None
) -> list[str]:
    if not rows or not drawn:
        return []
    index = {name: i for i, name in enumerate(rows[0])}
    if "Firm" not in index:
        return ["Black book: no Firm column, edits not read"]
    wanted = {
        n: index[n]
        for n in ("Kind of job", "Firm", *contract.BLACK_BOOK_HAND_EDITABLE)
        if n in index
    }
    by_name = {s.name.casefold(): s for s in suppliers}

    warnings: list[str] = []
    for raw in rows[1:]:
        cell = _cells(raw, wanted)
        firm = _plain(cell["Firm"])
        if not firm:
            continue
        supplier = by_name.get(firm.casefold())
        if supplier is None:
            warnings.append(f"Black book: no firm called '{firm}'")
            continue
        was = drawn.get(black_book_key({"Kind of job": cell.get("Kind of job", ""), "Firm": firm}))
        if was is None:
            warnings.append(f"Black book: '{firm}' was not drawn here; edits ignored")
            continue

        def changed(header: str, cell=cell, was=was) -> bool:
            return _edited(cell.get(header, ""), was, header)

        if changed("Contact"):
            supplier.contact_name = cell["Contact"]
        if changed("Phone"):
            supplier.phone = _phone(cell["Phone"])
        if changed("Email"):
            supplier.email = cell["Email"]
        if cell.get("Contract ends"):
            day = _parse_date(cell["Contract ends"])
            if day is None:
                if not _same(cell["Contract ends"], was.get("Contract ends", "")):
                    warnings.append(
                        f"Black book: '{cell['Contract ends']}' is not a date, ignored for {firm}"
                    )
            elif day != _parse_date(was.get("Contract ends", "")):
                supplier.contract_ends = day
        if changed("Notice to give"):
            days = cell["Notice to give"]
            if days.isdigit():
                supplier.notice_days = int(days)
            else:
                warnings.append(f"Black book: '{days}' is not a number of days, ignored for {firm}")
    return warnings
