"""Apply watcher observations to request records."""

from __future__ import annotations

import datetime as dt

from xsource.store.models import Request
from xsource.watcher.parser import ParsedReply
from xsource.workbook.stages import record_price


def _iso(when: dt.datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return when.astimezone(dt.UTC).isoformat()


def mark_thread_sent(request: Request, *, thread_id: str, sent_at: dt.datetime) -> bool:
    for entry in request.shortlist:
        if entry.outreach.get("thread_id") != thread_id:
            continue
        entry.outreach["status"] = "asked"
        entry.outreach["asked_at"] = _iso(sent_at)
        # A follow-up sent after a price or a decline must not wind the firm back.
        if entry.stage not in ("Quoted", "Booked", "Declined", "Not chosen"):
            entry.stage = "Emailed"
        entry.last_contact = {"date": sent_at.date().isoformat(), "via": "email"}
        return True
    return False


def apply_reply_to_request(
    request: Request,
    *,
    thread_id: str,
    parsed: ParsedReply,
    received_at: dt.datetime,
) -> bool:
    for entry in request.shortlist:
        if entry.outreach.get("thread_id") != thread_id:
            continue
        entry.reply = {
            "status": parsed.status,
            "quote_amount": parsed.quote_amount,
            "currency": parsed.currency,
            "includes": parsed.includes,
            "availability": parsed.availability,
            "conditions": parsed.conditions,
            "declined": parsed.declined,
            "summary": parsed.summary,
            "source_span": parsed.source_span,
            "received_at": _iso(received_at),
        }
        if parsed.quote_amount is not None:
            record_price(
                entry,
                round(parsed.quote_amount * 100),
                on=received_at.date(),
                via="email",
            )
        if parsed.declined:
            entry.stage = "Declined"
        return True
    return False
