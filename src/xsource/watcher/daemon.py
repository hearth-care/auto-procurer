"""One-cycle reply watcher orchestration.

The long-running launchd loop calls ``process_once`` repeatedly. Keeping this
function pure-ish and injectable makes the Gmail/Sheets behaviour testable
without live credentials.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from xsource.store.models import Request, Supplier
from xsource.watcher.apply import apply_reply_to_request, mark_thread_sent
from xsource.watcher.parser import parse_supplier_reply


@dataclass(frozen=True)
class WatcherMessage:
    id: str
    thread_id: str
    from_addr: str
    body: str
    received_at: dt.datetime
    is_outbound: bool = False


def _iso(when: dt.datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return when.astimezone(dt.UTC).isoformat()


def _open_requests(requests) -> list[Request]:
    return [request for request in requests.all() if getattr(request, "status", "") == "open"]


def _thread_ids(request: Request) -> set[str]:
    return {
        str(entry.outreach.get("thread_id"))
        for entry in request.shortlist
        if entry.outreach.get("thread_id")
    }


def _supplier_by_id(suppliers) -> dict[str, Supplier]:
    return {supplier.id: supplier for supplier in suppliers.all()}


def _flag_possible_replies(
    *,
    request: Request,
    suppliers_by_id: dict[str, Supplier],
    recent_messages: list[WatcherMessage],
    known_threads: set[str],
) -> int:
    possible = list(request.watcher.get("possible_replies", []))
    seen_ids = {item.get("message_id") for item in possible}
    supplier_emails = {
        (supplier.email or "").lower(): supplier.id
        for supplier in suppliers_by_id.values()
        if supplier.email
    }
    added = 0
    for message in recent_messages:
        if message.is_outbound or message.thread_id in known_threads or message.id in seen_ids:
            continue
        supplier_id = supplier_emails.get(message.from_addr.lower())
        if supplier_id not in {entry.supplier_id for entry in request.shortlist}:
            continue
        possible.append(
            {
                "message_id": message.id,
                "thread_id": message.thread_id,
                "supplier_id": supplier_id,
                "from": message.from_addr,
                "received_at": _iso(message.received_at),
                "status": "needs_review",
            }
        )
        added += 1
    if possible:
        request.watcher["possible_replies"] = possible
    return added


def _entry_rank_for_thread(request: Request, thread_id: str) -> int | None:
    for entry in request.shortlist:
        if entry.outreach.get("thread_id") == thread_id:
            return entry.rank
    return None


def process_once(
    *,
    requests,
    suppliers,
    gmail,
    sheets,
    gateway,
    state,
    now: dt.datetime,
) -> dict[str, int]:
    processed = 0
    possible_replies = 0
    supplier_records = _supplier_by_id(suppliers)
    open_requests = _open_requests(requests)
    if not open_requests:
        return {"processed": processed, "possible_replies": possible_replies}
    recent_messages = gmail.list_recent_messages()

    for request in open_requests:
        known_threads = _thread_ids(request)
        for thread_id in known_threads:
            for message in gmail.list_thread_messages(thread_id):
                if state.seen(message.id):
                    continue
                rank = _entry_rank_for_thread(request, thread_id)
                if rank is None:
                    continue
                if message.is_outbound:
                    if mark_thread_sent(request, thread_id=thread_id, sent_at=message.received_at):
                        if request.sheet_id:
                            sheets.mark_asked(
                                request.sheet_id,
                                rank=rank,
                                asked_at=message.received_at,
                                updated_at=now,
                            )
                        state.mark_processed(message.id, "sent")
                        processed += 1
                    continue
                parsed = parse_supplier_reply(message.body, gateway)
                if apply_reply_to_request(
                    request,
                    thread_id=thread_id,
                    parsed=parsed,
                    received_at=message.received_at,
                ):
                    if request.sheet_id:
                        sheets.write_reply(
                            request.sheet_id,
                            rank=rank,
                            parsed=parsed,
                            received_at=message.received_at,
                            updated_at=now,
                        )
                    state.mark_processed(message.id, "parsed")
                    processed += 1
        possible_replies += _flag_possible_replies(
            request=request,
            suppliers_by_id=supplier_records,
            recent_messages=recent_messages,
            known_threads=known_threads,
        )
        request.watcher["last_checked_at"] = _iso(now)
        if request.sheet_id:
            sheets.update_heartbeat(request.sheet_id, now)
        requests.upsert(request)

    return {"processed": processed, "possible_replies": possible_replies}
