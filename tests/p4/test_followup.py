from __future__ import annotations

import datetime as dt

from xsource.p4.followup import create_followup_draft
from xsource.store.models import Request, ShortlistEntry, Supplier


class _DraftClient:
    def __init__(self):
        self.calls = []

    def create_draft(self, *, to, subject, body, label):
        self.calls.append({"to": to, "subject": subject, "body": body, "label": label})
        return {"draft_id": "fd-1", "message_id": "fm-1", "thread_id": "thr-1"}


def test_create_followup_draft_uses_existing_thread_reference_and_remains_draft_only():
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                outreach={"thread_id": "thr-1", "status": "asked"},
                reply={"summary": "Asked to visit before quoting.", "status": "replied"},
            )
        ],
    )
    supplier = Supplier(id="s-1", name="Tree Co", email="quotes@example.com")
    client = _DraftClient()

    result = create_followup_draft(
        request,
        supplier,
        draft_client=client,
        now=dt.datetime(2026, 6, 11, 10, 0, tzinfo=dt.UTC),
    )

    assert result == {"draft_id": "fd-1", "message_id": "fm-1", "thread_id": "thr-1"}
    assert client.calls[0]["label"] == "xsource/outbox"
    assert "ref r-0042" in client.calls[0]["body"]
    assert request.shortlist[0].outreach["followup_status"] == "draft_ready"
    assert "sent_at" not in request.shortlist[0].outreach
