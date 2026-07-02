from __future__ import annotations

import json
import logging

import pytest

from xsource.book import publish as publish_mod
from xsource.book.publish import (
    DIRECTORY_TITLE,
    DirectorySheetGone,
    publish_directory,
    save_directory_state,
)
from xsource.store.files import SyncedFile
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


class _FakeClient:
    def __init__(self, *, gone: bool = False):
        self.calls: list[tuple] = []
        self.gone = gone

    def create_directory_sheet(self, title, values, folder_id, share_with):
        self.calls.append(("create", title, len(values), folder_id, share_with))
        return "SID-1", "https://sheets.example/SID-1"

    def update_directory_sheet(self, sheet_id, values):
        if self.gone:
            raise DirectorySheetGone(sheet_id)
        self.calls.append(("update", sheet_id, len(values)))


def _state_file(tmp_path):
    return SyncedFile(tmp_path / "directory-sheet.json", blob=None)


def test_publish_first_run_creates_and_persists(tmp_path):
    client = _FakeClient()
    report = publish_directory(
        _SUPPLIERS,
        state_file=_state_file(tmp_path),
        client=client,
        title=DIRECTORY_TITLE,
        folder_id=None,
        share_with=None,
    )
    assert report == {
        "sheet_id": "SID-1",
        "sheet_url": "https://sheets.example/SID-1",
        "rows": 2,
        "created": True,
    }
    assert client.calls == [("create", DIRECTORY_TITLE, 3, None, None)]
    assert json.loads((tmp_path / "directory-sheet.json").read_text())["sheet_id"] == "SID-1"


def test_publish_updates_existing_sheet(tmp_path):
    state = _state_file(tmp_path)
    save_directory_state(state, "SID-1", "https://sheets.example/SID-1")
    client = _FakeClient()
    report = publish_directory(
        _SUPPLIERS,
        state_file=state,
        client=client,
        title=DIRECTORY_TITLE,
        folder_id=None,
        share_with=None,
    )
    assert report["created"] is False
    assert report["sheet_id"] == "SID-1"
    assert client.calls == [("update", "SID-1", 3)]


def test_publish_recreates_when_gone(tmp_path):
    state = _state_file(tmp_path)
    save_directory_state(state, "SID-GONE", "https://sheets.example/SID-GONE")
    client = _FakeClient(gone=True)
    report = publish_directory(
        _SUPPLIERS,
        state_file=state,
        client=client,
        title=DIRECTORY_TITLE,
        folder_id=None,
        share_with=None,
    )
    assert report["created"] is True
    assert report["sheet_id"] == "SID-1"
    assert json.loads(state.path.read_text())["sheet_id"] == "SID-1"


def test_publish_empty_book_blocks(tmp_path):
    with pytest.raises(ValueError):
        publish_directory(
            [],
            state_file=_state_file(tmp_path),
            client=_FakeClient(),
            title=DIRECTORY_TITLE,
            folder_id=None,
            share_with=None,
        )


def test_publish_state_save_failure_still_reports(tmp_path, monkeypatch, caplog):
    def fail_save(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(publish_mod, "save_directory_state", fail_save)
    caplog.set_level(logging.WARNING, logger="xsource.book")
    report = publish_directory(
        _SUPPLIERS,
        state_file=_state_file(tmp_path),
        client=_FakeClient(),
        title=DIRECTORY_TITLE,
        folder_id=None,
        share_with=None,
    )
    assert report["sheet_id"] == "SID-1"
    assert "state save failed" in caplog.text


def test_publish_malformed_state_treated_as_absent(tmp_path):
    state = _state_file(tmp_path)
    state.path.write_text("not json")
    client = _FakeClient()
    report = publish_directory(
        _SUPPLIERS,
        state_file=state,
        client=client,
        title=DIRECTORY_TITLE,
        folder_id=None,
        share_with=None,
    )
    assert report["created"] is True
    assert client.calls == [("create", DIRECTORY_TITLE, 3, None, None)]
