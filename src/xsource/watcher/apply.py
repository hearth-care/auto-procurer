"""Apply watcher observations to request records."""

from __future__ import annotations

import datetime as dt

from xsource.store.models import Request
from xsource.watcher.parser import ParsedReply


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
        return True
    return False
