from __future__ import annotations

import datetime as dt

from xsource.cli.request import sync_all_requests
from xsource.store.models import Request, ShortlistEntry, Supplier


class _Store:
    def __init__(self, records):
        self.records = {record.id: record for record in records}
        self.upserted = []

    def all(self):
        return list(self.records.values())

    def get(self, rec_id):
        return self.records.get(rec_id)

    def upsert(self, record):
        self.records[record.id] = record
        self.upserted.append(record)


class _Sheets:
    def __init__(self):
        self.reads = []

    def read_request_rows(self, sheet_id):
        self.reads.append(sheet_id)
        return [{"rank": 1, "status": "Chosen", "quote": "185", "chosen": "yes", "notes": ""}]


def test_sync_all_requests_syncs_open_sheet_backed_requests_only():
    suppliers = _Store([Supplier(id="s-1", name="Tree Co")])
    requests = _Store(
        [
            Request(
                id="req-open",
                created_at="2026-06-10T15:58:00+00:00",
                raw_need="tree chipping",
                status="open",
                sheet_id="sheet-open",
                shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],
            ),
            Request(
                id="req-closed",
                created_at="2026-06-10T15:58:00+00:00",
                raw_need="tree chipping",
                status="closed",
                sheet_id="sheet-closed",
            ),
            Request(
                id="req-no-sheet",
                created_at="2026-06-10T15:58:00+00:00",
                raw_need="tree chipping",
                status="open",
            ),
        ]
    )
    sheets = _Sheets()

    report = sync_all_requests(
        suppliers=suppliers,
        requests=requests,
        sheets=sheets,
        synced_at=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )

    assert sheets.reads == ["sheet-open"]
    assert report == {
        "synced_requests": 1,
        "updated_suppliers": 1,
        "warnings": ["req-no-sheet has no sheet_id"],
    }
    assert requests.get("req-open").status == "closed"
    assert requests.upserted == [requests.get("req-open")]
