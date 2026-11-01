from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from xsource.store.models import LogEntry, Request, ShortlistEntry, Supplier
from xsource.workbook import contract

_LONDON = ZoneInfo("Europe/London")
_TAB_FORBIDDEN = re.compile(r"[\[\]*?:/\\]")
_MAX_TAB = 90


def uk_phone(phone: str | None) -> str:
    digits = "".join(ch for ch in phone or "" if ch.isdigit() or ch == "+")
    if digits.startswith("+44"):
        digits = "0" + digits[3:]
    if len(digits) != 11 or not digits.startswith("0"):
        return phone or ""
    if digits.startswith("02"):
        return f"{digits[:3]} {digits[3:7]} {digits[7:]}"
    return f"{digits[:5]} {digits[5:]}"


def phone_cell(phone: str | None) -> str:
    shown = uk_phone(phone)
    return f"'{shown}" if shown else ""


def job_tab_name(title: str, created: dt.date, existing: set[str]) -> str:
    base = " ".join(_TAB_FORBIDDEN.sub("", title).split())
    suffix = f" {created:%b %Y}"
    taken = {n.casefold() for n in existing}

    def build(tail: str) -> str:
        room = _MAX_TAB - len(suffix) - len(tail)
        return f"{base[:room].rstrip()}{suffix}{tail}"

    name, n = build(""), 1
    while name.casefold() in taken:
        n += 1
        name = build(f" ({n})")
    return name


def quote_tab(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _text(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _link(target: str, label: str) -> str:
    return f"=HYPERLINK({_text(target)},{_text(label)})"


def _pounds(minor: int | None) -> str:
    if minor is None:
        return ""
    whole, pence = divmod(minor, 100)
    return str(whole) if pence == 0 else f"{minor / 100:.2f}"


def _price_col(energy: bool) -> str:
    return "M" if energy else "K"


def board_rows(requests: list[Request], start_row: int = 2) -> list[list[str]]:
    jobs = sorted(
        (r for r in requests if r.status == "open" and r.job_tab),
        key=lambda r: r.created_at,
        reverse=True,
    )
    rows = []
    for i, r in enumerate(jobs):
        row = start_row + i
        tab = quote_tab(r.job_tab or "")
        p = _price_col(r.energy)
        keen = "+".join(f'COUNTIF({tab}!I:I,"{s}")' for s in contract.KEEN_STAGES)
        rows.append(
            [
                r.title or "",
                _link(f"#gid={r.job_tab_gid}", r.job_tab or ""),
                r.stage,
                f"={keen}",
                f"=COUNT({tab}!{p}2:{p})",
                f'=IF(E{row}=0,"",MIN({tab}!{p}:{p}))',
                f'=IF(E{row}=0,"",INDEX({tab}!B:B, MATCH(MIN({tab}!{p}:{p}), {tab}!{p}:{p}, 0)))',
                r.next_step,
                r.waiting_on,
            ]
        )
    return rows


def _last_contact(entry: ShortlistEntry) -> str:
    raw = entry.last_contact.get("date")
    if not raw:
        return ""
    try:
        day = dt.date.fromisoformat(raw[:10])
    except ValueError:
        return ""
    when = f"{day.day} {day:%b}"
    via = entry.last_contact.get("via")
    return f"{when} · {via}" if via else when


def _thread_link(entry: ShortlistEntry) -> str:
    thread_id = entry.outreach.get("thread_id")
    if not thread_id:
        return ""
    return _link(f"https://mail.google.com/mail/u/0/#all/{thread_id}", "thread")


def job_tab_rows(request: Request, suppliers: dict[str, Supplier]) -> list[list[str]]:
    energy = request.energy
    rows = [list(contract.ENERGY_JOB_COLUMNS if energy else contract.JOB_COLUMNS)]
    for e in sorted(request.shortlist, key=lambda e: e.rank):
        if e.excluded:
            continue
        s = suppliers.get(e.supplier_id) or Supplier(id=e.supplier_id, name=e.supplier_id)
        head = [
            str(e.rank),
            s.name,
            e.contact_name or s.contact_name or "",
            phone_cell(s.phone),
            s.email or "",
            s.website or "",
            s.address or "",
            "" if e.miles is None else f"{e.miles:g}",
            e.stage,
        ]
        if energy:
            q = e.energy_quote
            money = [
                str(q.get("term", "")),
                str(q.get("unit_rate", "")),
                str(q.get("standing_charge", "")),
                _pounds(e.latest_price_minor),
            ]
            tail = [_last_contact(e), "", _thread_link(e), e.notes]
        else:
            money = [_pounds(e.first_price_minor), _pounds(e.latest_price_minor)]
            tail = [_last_contact(e), "", _thread_link(e), e.notes]
        rows.append([*head, *money, *tail])
    return rows


def _iso_date(raw: str | None) -> str:
    return (raw or "")[:10]


def black_book_rows(suppliers: list[Supplier], requests: list[Request]) -> list[list[str]]:
    by_id = {s.id: s for s in suppliers}
    # kind -> (recency key, supplier, deciding request or None); the newest firm wins each kind.
    chosen: dict[str, tuple[str, Supplier, Request | None]] = {}

    def consider(kind: str, key: str, s: Supplier, r: Request | None) -> None:
        if kind not in chosen or key > chosen[kind][0]:
            chosen[kind] = (key, s, r)

    for req in requests:
        s = by_id.get(req.chosen_supplier_id or "")
        kind = req.triage.get("category")
        if req.status == "closed" and s is not None and kind:
            consider(kind, req.created_at, s, req)
    for s in suppliers:
        if s.preferred and s.categories:
            consider(s.categories[0], _iso_date(s.last_used), s, None)

    rows = [list(contract.BLACK_BOOK_COLUMNS)]
    for kind in sorted(chosen):
        _, s, r = chosen[kind]
        entry = next((e for e in r.shortlist if e.supplier_id == s.id), None) if r else None
        n = len(rows) + 1
        rows.append(
            [
                kind,
                s.name,
                (entry.contact_name if entry else None) or s.contact_name or "",
                phone_cell(s.phone),
                s.email or "",
                _iso_date(s.last_used),
                _pounds(entry.latest_price_minor) if entry else "",
                _iso_date(s.contract_ends),
                "" if s.notice_days is None else str(s.notice_days),
                f'=IF(H{n}="","",H{n}-I{n})',
                _link(f"https://drive.google.com/drive/folders/{s.drive_folder_id}", "folder")
                if s.drive_folder_id
                else "",
                _link(f"#gid={r.job_tab_gid}", r.job_tab) if r and r.job_tab else "",
                "TRUE" if s.in_xero else "FALSE",
            ]
        )
    return rows


def _london(at: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(at)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(_LONDON)


def log_rows(entries: list[LogEntry], requests: dict[str, Request]) -> list[list[str]]:
    rows = [list(contract.LOG_COLUMNS)]
    for e in sorted(entries, key=lambda e: _london(e.at), reverse=True):
        r = requests.get(e.request_id or "")
        rows.append(
            [
                f"{_london(e.at):%Y-%m-%d %H:%M}",
                (r.job_tab or r.title or "") if r else "",
                e.text,
            ]
        )
    return rows
