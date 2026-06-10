from __future__ import annotations

import datetime as dt

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.watcher.daemon import WatcherMessage, process_once
from xsource.watcher.state import ProcessedMessageStore


class _Store:
    def __init__(self, records):
        self.records = {record.id: record for record in records}
        self.upserted = []

    def all(self):
        return list(self.records.values())

    def get(self, rec_id):
        return self.records.get(rec_id)

    def upsert(self, rec):
        self.records[rec.id] = rec
        self.upserted.append(rec)


class _Gmail:
    def __init__(self, thread_messages=None, recent_messages=None):
        self.thread_messages = thread_messages or {}
        self.recent_messages = recent_messages or []
        self.recent_calls = 0

    def list_thread_messages(self, thread_id):
        return list(self.thread_messages.get(thread_id, []))

    def list_recent_messages(self):
        self.recent_calls += 1
        return list(self.recent_messages)


class _Gateway:
    def complete_structured(self, messages, schema, role="research"):
        return {
            "quote_amount": 185,
            "currency": "GBP",
            "includes": "cut and chip",
            "availability": "Thursday",
            "conditions": None,
            "declined": False,
            "summary": "Quoted £185 and can attend Thursday.",
            "source_span": "£185",
        }


class _Sheets:
    def __init__(self):
        self.asked = []
        self.replies = []
        self.heartbeats = []

    def mark_asked(self, sheet_id, *, rank, asked_at, updated_at):
        self.asked.append((sheet_id, rank, asked_at, updated_at))

    def write_reply(self, sheet_id, *, rank, parsed, received_at, updated_at):
        self.replies.append((sheet_id, rank, parsed.status, received_at, updated_at))

    def update_heartbeat(self, sheet_id, checked_at):
        self.heartbeats.append((sheet_id, checked_at))


def _request():
    return Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        status="open",
        sheet_id="sheet-1",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-1",
                rank=1,
                outreach={"thread_id": "thr-1", "status": "draft_ready"},
            )
        ],
    )


def test_process_once_marks_sent_and_parses_supplier_reply_idempotently(tmp_path):
    request = _request()
    requests = _Store([request])
    suppliers = _Store([Supplier(id="s-1", name="Tree Co", email="tree@example.com")])
    gmail = _Gmail(
        {
            "thr-1": [
                WatcherMessage(
                    id="out-1",
                    thread_id="thr-1",
                    from_addr="milo.garth@clonwaycare.co.uk",
                    body="our draft",
                    received_at=dt.datetime(2026, 6, 10, 16, 5, tzinfo=dt.UTC),
                    is_outbound=True,
                ),
                WatcherMessage(
                    id="in-1",
                    thread_id="thr-1",
                    from_addr="tree@example.com",
                    body="£185 Thursday",
                    received_at=dt.datetime(2026, 6, 11, 9, 38, tzinfo=dt.UTC),
                    is_outbound=False,
                ),
            ]
        }
    )
    sheets = _Sheets()
    state = ProcessedMessageStore(tmp_path / "watcher.sqlite3")

    first = process_once(
        requests=requests,
        suppliers=suppliers,
        gmail=gmail,
        sheets=sheets,
        gateway=_Gateway(),
        state=state,
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )
    second = process_once(
        requests=requests,
        suppliers=suppliers,
        gmail=gmail,
        sheets=sheets,
        gateway=_Gateway(),
        state=state,
        now=dt.datetime(2026, 6, 11, 9, 41, tzinfo=dt.UTC),
    )

    saved = requests.get("r-0042")
    assert first == {"processed": 2, "possible_replies": 0}
    assert second == {"processed": 0, "possible_replies": 0}
    assert saved.shortlist[0].outreach["status"] == "asked"
    assert saved.shortlist[0].reply["status"] == "quoted"
    assert saved.watcher["last_checked_at"] == "2026-06-11T09:41:00+00:00"
    assert len(sheets.asked) == 1
    assert len(sheets.replies) == 1
    assert len(sheets.heartbeats) == 2


def test_process_once_flags_off_thread_reply_without_parsing(tmp_path):
    request = _request()
    requests = _Store([request])
    suppliers = _Store([Supplier(id="s-1", name="Tree Co", email="tree@example.com")])
    gmail = _Gmail(
        recent_messages=[
            WatcherMessage(
                id="off-1",
                thread_id="other-thread",
                from_addr="tree@example.com",
                body="I replied separately.",
                received_at=dt.datetime(2026, 6, 11, 9, 38, tzinfo=dt.UTC),
                is_outbound=False,
            )
        ]
    )

    report = process_once(
        requests=requests,
        suppliers=suppliers,
        gmail=gmail,
        sheets=_Sheets(),
        gateway=_Gateway(),
        state=ProcessedMessageStore(tmp_path / "watcher.sqlite3"),
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )

    saved = requests.get("r-0042")
    assert report == {"processed": 0, "possible_replies": 1}
    assert saved.shortlist[0].reply == {}
    assert saved.watcher["possible_replies"][0]["message_id"] == "off-1"


def test_process_once_skips_gmail_recent_scan_when_no_open_requests(tmp_path):
    gmail = _Gmail()

    report = process_once(
        requests=_Store([]),
        suppliers=_Store([]),
        gmail=gmail,
        sheets=_Sheets(),
        gateway=_Gateway(),
        state=ProcessedMessageStore(tmp_path / "watcher.sqlite3"),
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )

    assert report == {"processed": 0, "possible_replies": 0}
    assert gmail.recent_calls == 0
