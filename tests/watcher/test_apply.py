from __future__ import annotations

import datetime as dt

from xsource.store.models import Request, ShortlistEntry
from xsource.watcher.apply import apply_reply_to_request, mark_thread_sent
from xsource.watcher.parser import ParsedReply


def test_mark_thread_sent_flips_matching_thread_to_asked():
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                outreach={"thread_id": "thr-1", "status": "draft_ready"},
            )
        ],
    )

    changed = mark_thread_sent(
        request,
        thread_id="thr-1",
        sent_at=dt.datetime(2026, 6, 10, 16, 5, tzinfo=dt.UTC),
    )

    assert changed is True
    assert request.shortlist[0].outreach["status"] == "asked"
    assert request.shortlist[0].outreach["asked_at"] == "2026-06-10T16:05:00+00:00"


def test_apply_reply_to_request_updates_reply_without_closing_request():
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1, outreach={"thread_id": "thr-1"})],
    )
    parsed = ParsedReply(
        status="quoted",
        quote_amount=185,
        currency="GBP",
        includes="cut and chip",
        availability="Thursday",
        conditions=None,
        declined=False,
        summary="Quoted £185 and can attend Thursday.",
        source_span="£185",
    )

    changed = apply_reply_to_request(
        request,
        thread_id="thr-1",
        parsed=parsed,
        received_at=dt.datetime(2026, 6, 11, 9, 38, tzinfo=dt.UTC),
    )

    assert changed is True
    assert request.status == "open"
    assert request.shortlist[0].reply["status"] == "quoted"
    assert request.shortlist[0].reply["quote_amount"] == 185
    assert request.shortlist[0].reply["received_at"] == "2026-06-11T09:38:00+00:00"
