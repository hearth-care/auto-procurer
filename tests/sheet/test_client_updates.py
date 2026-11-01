from __future__ import annotations

from xsource.sheet.client import SheetClient


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

    assert rows == [
        {"rank": 1, "status": "Chosen", "quote": "185", "chosen": "yes", "notes": "good"}
    ]
