from __future__ import annotations

import datetime as dt

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.watcher.daemon import ThreadMissing, WatcherMessage, process_once
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


class _Redraw:
    def __init__(self):
        self.call_count = 0

    def __call__(self):
        self.call_count += 1


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
    redraw = _Redraw()
    state = ProcessedMessageStore(tmp_path / "watcher.sqlite3")

    first = process_once(
        requests=requests,
        suppliers=suppliers,
        gmail=gmail,
        redraw_fn=redraw,
        gateway=_Gateway(),
        state=state,
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )
    second = process_once(
        requests=requests,
        suppliers=suppliers,
        gmail=gmail,
        redraw_fn=redraw,
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
    assert saved.shortlist[0].stage == "Quoted"
    assert saved.shortlist[0].latest_price_minor == 18500
    assert redraw.call_count == 1


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
        redraw_fn=None,
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
        redraw_fn=None,
        gateway=_Gateway(),
        state=ProcessedMessageStore(tmp_path / "watcher.sqlite3"),
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )

    assert report == {"processed": 0, "possible_replies": 0}
    assert gmail.recent_calls == 0


def test_a_missing_thread_is_recorded_and_the_other_suppliers_are_still_watched(tmp_path):
    request = _request()
    request.shortlist.append(
        ShortlistEntry(supplier_id="s-2", rank=2, outreach={"thread_id": "thr-gone"})
    )
    reply = WatcherMessage(
        id="in-1",
        thread_id="thr-1",
        from_addr="tree@example.com",
        body="£185 Thursday",
        received_at=dt.datetime(2026, 6, 11, 9, 38, tzinfo=dt.UTC),
    )

    class _GmailWithDeadThread(_Gmail):
        def list_thread_messages(self, thread_id):
            if thread_id == "thr-gone":
                raise ThreadMissing(thread_id)
            return super().list_thread_messages(thread_id)

    requests = _Store([request])
    kwargs = dict(
        requests=requests,
        suppliers=_Store([Supplier(id="s-1", name="Tree Co", email="tree@example.com")]),
        redraw_fn=None,
        gateway=_Gateway(),
        state=ProcessedMessageStore(tmp_path / "watcher.sqlite3"),
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )

    result = process_once(gmail=_GmailWithDeadThread({"thr-1": [reply]}), **kwargs)

    saved = requests.get("r-0042")
    assert result["processed"] == 1
    assert saved.shortlist[0].reply["status"] == "quoted"
    assert saved.watcher["missing_threads"] == ["thr-gone"]

    saved.shortlist[1].outreach["thread_id"] = "thr-1"
    process_once(gmail=_Gmail({"thr-1": [reply]}), **kwargs)
    assert "missing_threads" not in requests.get("r-0042").watcher


_OWN = "milo.garth@clonwaycare.co.uk"


def _own_message(message_id, *, draft):
    return WatcherMessage(
        id=message_id,
        thread_id="thr-1",
        from_addr=_OWN,
        body="our email",
        received_at=dt.datetime(2026, 6, 10, 16, 5, tzinfo=dt.UTC),
        is_outbound=True,
        is_draft=draft,
    )


def _cycle(request, messages, tmp_path, redraw):
    state = ProcessedMessageStore(tmp_path / "watcher.sqlite3")
    result = process_once(
        requests=_Store([request]),
        suppliers=_Store([Supplier(id="s-1", name="Tree Co", email="tree@example.com")]),
        gmail=_Gmail({"thr-1": messages}),
        redraw_fn=redraw,
        gateway=_Gateway(),
        state=state,
        now=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )
    return result, state


def test_a_draft_in_the_thread_is_not_counted_as_sent(tmp_path):
    request = _request()
    request.shortlist[0].stage = "Keen"
    redraw = _Redraw()

    result, state = _cycle(request, [_own_message("draft-1", draft=True)], tmp_path, redraw)

    assert result["processed"] == 0
    assert request.shortlist[0].stage == "Keen"
    assert request.shortlist[0].outreach["status"] == "draft_ready"
    assert redraw.call_count == 0
    assert not state.seen("draft-1")


def test_the_sent_message_moves_the_firm_to_emailed_and_redraws_once(tmp_path):
    request = _request()
    request.shortlist[0].stage = "Keen"
    redraw = _Redraw()

    _cycle(request, [_own_message("sent-1", draft=False)], tmp_path, redraw)

    entry = request.shortlist[0]
    assert entry.stage == "Emailed"
    assert entry.last_contact == {"date": "2026-06-10", "via": "email"}
    assert redraw.call_count == 1


def test_a_quoted_reply_records_the_price_in_pence(tmp_path):
    request = _request()
    reply = WatcherMessage(
        id="in-1",
        thread_id="thr-1",
        from_addr="tree@example.com",
        body="£185 Thursday",
        received_at=dt.datetime(2026, 6, 11, 9, 38, tzinfo=dt.UTC),
    )

    _cycle(request, [reply], tmp_path, _Redraw())

    entry = request.shortlist[0]
    assert entry.latest_price_minor == 18500
    assert entry.first_price_minor == 18500
    assert entry.stage == "Quoted"


def test_a_cycle_with_nothing_new_does_not_redraw(tmp_path):
    redraw = _Redraw()

    _cycle(_request(), [], tmp_path, redraw)

    assert redraw.call_count == 0


def test_a_request_with_only_a_legacy_sheet_id_is_still_processed_without_sheet_calls(tmp_path):
    request = _request()
    result, _ = _cycle(request, [_own_message("sent-1", draft=False)], tmp_path, None)

    assert result["processed"] == 1
    assert request.shortlist[0].outreach["status"] == "asked"
