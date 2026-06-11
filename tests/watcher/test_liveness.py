"""Two-cycle end-to-end liveness test.

Wires the real ``process_once`` through the real ``run_loop`` using fake
collaborators injected at the factory seam (no live Gmail / Sheets / GCS
credentials required).

Cycle 1 — parse and persist an inbound supplier reply.
Cycle 2 — idempotent: same messages, state already marked, nothing re-processed.

Heartbeats must advance between cycles; the processed count must be non-zero
on cycle 1 and zero on cycle 2.
"""

from __future__ import annotations

import datetime as dt

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.watcher.daemon import WatcherMessage, process_once
from xsource.watcher.loop import run_loop
from xsource.watcher.state import ProcessedMessageStore


class _FakeStore:
    """In-memory store (always online)."""

    def __init__(self, records):
        self.records = {r.id: r for r in records}
        self.offline = False

    def all(self):
        return list(self.records.values())

    def get(self, rec_id):
        return self.records.get(rec_id)

    def upsert(self, rec):
        self.records[rec.id] = rec


class _FakeGmail:
    def __init__(self, thread_messages, recent_messages=None):
        self.thread_messages = thread_messages
        self.recent_messages = recent_messages or []

    def list_thread_messages(self, thread_id):
        return list(self.thread_messages.get(thread_id, []))

    def list_recent_messages(self):
        return list(self.recent_messages)


class _FakeGateway:
    def complete_structured(self, messages, schema, role="research"):
        return {
            "quote_amount": 250,
            "currency": "GBP",
            "includes": "labour and materials",
            "availability": "Monday",
            "conditions": None,
            "declined": False,
            "summary": "Quoted £250 all-in for Monday.",
            "source_span": "£250",
        }


class _FakeSheets:
    def __init__(self):
        self.heartbeats = []
        self.replies = []

    def mark_asked(self, sheet_id, *, rank, asked_at, updated_at):
        pass

    def write_reply(self, sheet_id, *, rank, parsed, received_at, updated_at):
        self.replies.append(parsed.quote_amount)

    def update_heartbeat(self, sheet_id, checked_at):
        self.heartbeats.append(checked_at)


def _make_fixtures():
    request = Request(
        id="r-live-1",
        created_at="2026-06-10T08:00:00+00:00",
        raw_need="roof repair",
        status="open",
        sheet_id="sheet-live",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-roof",
                rank=1,
                outreach={"thread_id": "thr-live", "status": "asked", "asked_at": "2026-06-10T09:00:00+00:00"},
            )
        ],
    )
    supplier = Supplier(id="s-roof", name="Roof Co", email="roof@example.com")
    messages = {
        "thr-live": [
            WatcherMessage(
                id="msg-live-1",
                thread_id="thr-live",
                from_addr="roof@example.com",
                body="Happy to help. £250 all-in, available Monday.",
                received_at=dt.datetime(2026, 6, 11, 10, 0, tzinfo=dt.UTC),
                is_outbound=False,
            )
        ]
    }
    return request, supplier, messages


def test_two_cycle_liveness(tmp_path):
    request, supplier, messages = _make_fixtures()
    requests_store = _FakeStore([request])
    suppliers_store = _FakeStore([supplier])
    gmail = _FakeGmail(messages)
    gateway = _FakeGateway()
    sheets = _FakeSheets()
    state = ProcessedMessageStore(tmp_path / "watcher.sqlite3")

    cycle_results = []

    def _run_once():
        now = dt.datetime(2026, 6, 11, 10, 0 + len(cycle_results), tzinfo=dt.UTC)
        result = process_once(
            requests=requests_store,
            suppliers=suppliers_store,
            gmail=gmail,
            sheets=sheets,
            gateway=gateway,
            state=state,
            now=now,
        )
        cycle_results.append(result)
        return result

    run_loop(_run_once, poll_seconds=0, sleep_fn=lambda _: None, max_cycles=2)

    # Cycle 1: parsed one inbound reply
    assert cycle_results[0]["processed"] == 1
    # Cycle 2: idempotent — same messages already marked, nothing re-processed
    assert cycle_results[1]["processed"] == 0

    saved = requests_store.get("r-live-1")
    assert saved.shortlist[0].reply["status"] == "quoted"
    assert saved.shortlist[0].reply["quote_amount"] == 250

    # Heartbeats advanced in both cycles
    assert len(sheets.heartbeats) == 2
    assert sheets.heartbeats[0] != sheets.heartbeats[1]

    # Reply written to sheets exactly once
    assert sheets.replies == [250]


def test_failed_upsert_does_not_mark_message_processed(tmp_path):
    """If requests.upsert raises, message must NOT be in the dedup store.

    This is the S2 ordering safety invariant: a failed persist never strands
    a message id so the next cycle can retry it.
    """
    request, supplier, messages = _make_fixtures()

    class _FailingStore(_FakeStore):
        def upsert(self, rec):
            raise RuntimeError("GCS unavailable")

    requests_store = _FailingStore([request])
    suppliers_store = _FakeStore([supplier])
    state = ProcessedMessageStore(tmp_path / "watcher.sqlite3")

    try:
        process_once(
            requests=requests_store,
            suppliers=suppliers_store,
            gmail=_FakeGmail(messages),
            sheets=_FakeSheets(),
            gateway=_FakeGateway(),
            state=state,
            now=dt.datetime(2026, 6, 11, 10, 0, tzinfo=dt.UTC),
        )
    except RuntimeError:
        pass

    # The message must NOT be marked as processed — it is still retryable
    assert not state.seen("msg-live-1")
