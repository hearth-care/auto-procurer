from __future__ import annotations

import datetime as dt

from xsource.sheet.client import SheetClient
from xsource.watcher.parser import ParsedReply


class _Executable:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def execute(self):
        return self.payload


class _Values:
    def __init__(self):
        self.batch_updates = []
        self.updates = []

    def batchUpdate(self, **kwargs):
        self.batch_updates.append(kwargs)
        return _Executable()

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return _Executable()


class _Spreadsheets:
    def __init__(self):
        self.values_obj = _Values()

    def values(self):
        return self.values_obj


class _Sheets:
    def __init__(self):
        self.spreadsheets_obj = _Spreadsheets()

    def spreadsheets(self):
        return self.spreadsheets_obj


class _Drive:
    pass


def _client():
    client = SheetClient.__new__(SheetClient)
    client.sheets = _Sheets()
    client.drive = _Drive()
    return client


def test_write_reply_batches_reply_quote_status_and_updated_cells():
    client = _client()
    parsed = ParsedReply(
        status="quoted",
        quote_amount=185,
        currency="GBP",
        includes="cut and chip",
        availability="Thursday",
        conditions=None,
        declined=False,
        summary="Quoted £185.",
        source_span="£185",
    )

    client.write_reply(
        "sheet-1",
        rank=2,
        parsed=parsed,
        received_at=dt.datetime(2026, 6, 11, 9, 38, tzinfo=dt.UTC),
        updated_at=dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC),
    )

    call = client.sheets.spreadsheets().values().batch_updates[0]
    assert call["spreadsheetId"] == "sheet-1"
    assert call["body"]["data"] == [
        {
            "range": "H3:M3",
            "values": [
                ["Quoted", "2026-06-11 09:38", "Quoted £185.", "185", "", "2026-06-11 09:40"]
            ],
        }
    ]


def test_update_heartbeat_writes_header_cell():
    client = _client()

    client.update_heartbeat("sheet-1", dt.datetime(2026, 6, 11, 9, 40, tzinfo=dt.UTC))

    call = client.sheets.spreadsheets().values().updates[0]
    assert call["spreadsheetId"] == "sheet-1"
    assert call["range"] == "A1"
    assert call["body"]["values"] == [["xsource last checked 2026-06-11 09:40"]]


def test_read_request_rows_maps_human_columns():
    client = _client()
    client.sheets.spreadsheets().values().get = lambda **_: _Executable(
        {
            "values": [
                [
                    "#",
                    "Provider",
                    "Source",
                    "Rating",
                    "Phone",
                    "Email",
                    "Indicative",
                    "Status",
                    "Asked",
                    "Reply",
                    "Quote £",
                    "Chosen",
                    "Updated",
                    "Notes",
                ],
                ["1", "Tree Co", "", "", "", "", "", "Chosen", "", "", "185", "yes", "", "good"],
            ]
        }
    )

    rows = client.read_request_rows("sheet-1")

    assert rows == [{"rank": 1, "status": "Chosen", "quote": "185", "chosen": "yes", "notes": "good"}]
