from __future__ import annotations

import pytest

from xsource.book.publish import DirectorySheetGone, build_directory_values
from xsource.sheet.client import SheetClient
from xsource.store.models import Supplier

_SUPPLIERS = [
    Supplier(
        id="s-0001",
        name="Alpha Tree Care",
        categories=["trees-grounds"],
        tags=["tree-surgery"],
        phone="+441632960001",
    ),
    Supplier(id="s-0002", name="Beta Heating", categories=["heating"], tags=["boiler"]),
]


class _Executable:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {}
        self.exc = exc

    def execute(self):
        if self.exc:
            raise self.exc
        return self.payload


class _Values:
    def __init__(self, *, update_exc=None):
        self.updates = []
        self.clears = []
        self.update_exc = update_exc

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return _Executable(exc=self.update_exc)

    def clear(self, **kwargs):
        self.clears.append(kwargs)
        return _Executable()


class _Spreadsheets:
    def __init__(self, *, update_exc=None):
        self.values_obj = _Values(update_exc=update_exc)
        self.creates = []

    def create(self, **kwargs):
        self.creates.append(kwargs)
        return _Executable(
            {"spreadsheetId": "SID-1", "spreadsheetUrl": "https://sheets.example/SID-1"}
        )

    def values(self):
        return self.values_obj


class _Sheets:
    def __init__(self, *, update_exc=None):
        self.spreadsheets_obj = _Spreadsheets(update_exc=update_exc)

    def spreadsheets(self):
        return self.spreadsheets_obj


class _Files:
    def __init__(self):
        self.updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return _Executable()


class _Permissions:
    def __init__(self):
        self.creates = []

    def create(self, **kwargs):
        self.creates.append(kwargs)
        return _Executable()


class _Drive:
    def __init__(self):
        self.files_obj = _Files()
        self.permissions_obj = _Permissions()

    def files(self):
        return self.files_obj

    def permissions(self):
        return self.permissions_obj


def _client(*, update_exc=None):
    client = SheetClient.__new__(SheetClient)
    client.sheets = _Sheets(update_exc=update_exc)
    client.drive = _Drive()
    return client


def test_directory_sheet_shared_read_only():
    client = _client()
    client.create_directory_sheet(
        "Supplier directory",
        build_directory_values(_SUPPLIERS),
        folder_id=None,
        share_with="staff@example.invalid",
    )

    call = client.drive.permissions().creates[0]
    assert call["body"] == {
        "type": "group",
        "role": "reader",
        "emailAddress": "staff@example.invalid",
    }
    assert call["sendNotificationEmail"] is False


def test_directory_values_written_raw():
    client = _client()
    values = build_directory_values(_SUPPLIERS)
    client.create_directory_sheet("Supplier directory", values, folder_id=None, share_with=None)
    client.update_directory_sheet("SID-1", values)

    updates = client.sheets.spreadsheets().values().updates
    assert updates[0]["valueInputOption"] == "RAW"
    assert updates[1]["valueInputOption"] == "RAW"


def test_update_clears_trailing_rows():
    client = _client()
    client.update_directory_sheet("SID-1", build_directory_values(_SUPPLIERS))
    assert client.sheets.spreadsheets().values().clears[0]["range"] == "A4:H"


def test_update_404_raises_gone():
    class _Resp:
        status = 404

    class _Http404(Exception):
        resp = _Resp()

    client = _client(update_exc=_Http404("missing"))
    with pytest.raises(DirectorySheetGone):
        client.update_directory_sheet("SID-GONE", build_directory_values(_SUPPLIERS))


def test_no_share_call_when_group_unset():
    client = _client()
    client.create_directory_sheet(
        "Supplier directory",
        build_directory_values(_SUPPLIERS),
        folder_id=None,
        share_with=None,
    )
    assert client.drive.permissions().creates == []
