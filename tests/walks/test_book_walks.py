from __future__ import annotations

from clonway_cockpit.walk import WizardContext
from rich.console import Console

from xsource.store.jsonl import JsonlStore
from xsource.store.models import Supplier

_CSV = """name,category,tags,phone,email,notes
Gamma Roofing,roofing,slate;flat-roof,01632 960100,gamma@example.com,synthetic seed row
Beta Heating,heating,boiler,01632 960101,,
"""


def _ctx(inputs: list[str]) -> WizardContext:
    it = iter(inputs)
    return WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda _prompt: next(it),
        confirm_fn=lambda _prompt: False,
    )


def _seeded_store(tmp_path):
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    store.upsert(Supplier(id="s-0002", name="Beta Heating"))
    return store


def _publish_store(tmp_path):
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    store.upsert(
        Supplier(
            id="s-0001",
            name="Alpha Tree Care",
            categories=["trees-grounds"],
            tags=["tree-surgery"],
            phone="+441632960001",
        )
    )
    store.upsert(Supplier(id="s-0002", name="Beta Heating", categories=["heating"]))
    return store


def test_book_import_declined_writes_nothing(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: False)
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = cockpit_mod._book_import_apply_step(_ctx([]), {"csv_path": str(csv_file)})
    assert result.ok is False
    assert result.message == "Apply declined."
    assert store.all() == []


def test_book_import_apply_writes_and_summarises(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = _seeded_store(tmp_path)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: True)
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = cockpit_mod._book_import_apply_step(_ctx([]), {"csv_path": str(csv_file)})
    assert result.ok is True
    assert result.data["summary"] == "Imported 1, skipped 1."
    assert {s.name for s in store.all()} == {"Beta Heating", "Gamma Roofing"}


def test_book_import_rerun_is_noop(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = _seeded_store(tmp_path)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: True)
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    cockpit_mod._book_import_apply_step(_ctx([]), {"csv_path": str(csv_file)})
    before = store.path.read_bytes()
    result = cockpit_mod._book_import_apply_step(_ctx([]), {"csv_path": str(csv_file)})
    assert result.data["summary"] == "Imported 0, skipped 2."
    assert store.path.read_bytes() == before


def test_book_import_file_step_rejects_missing_path(tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    result = cockpit_mod._book_import_file_step(_ctx([str(tmp_path / "absent.csv")]), {})
    assert result.ok is False
    assert result.message.startswith("No such file:")


def test_book_write_preflight_blocks_offline(monkeypatch):
    from xsource.cli import cockpit as cockpit_mod

    class _Offline:
        offline = True

    monkeypatch.setattr(
        cockpit_mod,
        "build_stores",
        lambda cfg: (_Offline(), object(), object()),
    )
    rows = cockpit_mod._book_write_preconditions(_ctx([]))
    assert rows[0].label == "Store reachable"
    assert rows[0].ok is False


def test_book_publish_declined_writes_nothing(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: False)
    monkeypatch.setattr(
        cockpit_mod,
        "publish_directory",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("publish called")),
    )
    result = cockpit_mod._book_publish_apply_step(_ctx([]), {})
    assert result.ok is False
    assert result.message == "Apply declined."


def test_book_publish_apply_summary(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setenv("XSOURCE_SHEETS_TOKEN_PATH", str(token))
    store = _publish_store(tmp_path)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    monkeypatch.setattr(cockpit_mod, "build_directory_state_file", lambda cfg: object())
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: True)
    monkeypatch.setattr(cockpit_mod, "SheetClient", lambda creds: object())

    class _Creds:
        @staticmethod
        def from_authorized_user_file(path):
            return object()

    monkeypatch.setattr(cockpit_mod, "Credentials", _Creds)
    monkeypatch.setattr(
        cockpit_mod,
        "publish_directory",
        lambda suppliers, **kwargs: {
            "sheet_id": "SID-1",
            "sheet_url": "https://sheets.example/SID-1",
            "rows": 2,
            "created": True,
        },
    )
    result = cockpit_mod._book_publish_apply_step(_ctx([]), {})
    assert result.ok is True
    assert result.data["summary"] == "Published directory (2 supplier(s))."
    assert result.data["result_links"] == [("Directory", "https://sheets.example/SID-1")]


def test_publish_apply_step_reports_api_error(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setenv("XSOURCE_SHEETS_TOKEN_PATH", str(token))
    store = _publish_store(tmp_path)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    monkeypatch.setattr(cockpit_mod, "build_directory_state_file", lambda cfg: object())
    monkeypatch.setattr(cockpit_mod, "confirm_apply", lambda *a, **k: True)
    monkeypatch.setattr(cockpit_mod, "SheetClient", lambda creds: object())

    class _Creds:
        @staticmethod
        def from_authorized_user_file(path):
            return object()

    monkeypatch.setattr(cockpit_mod, "Credentials", _Creds)
    monkeypatch.setattr(
        cockpit_mod,
        "publish_directory",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = cockpit_mod._book_publish_apply_step(_ctx([]), {})
    assert result.ok is False
    assert result.message == "Publish failed: boom"


def test_book_publish_preview_blocks_empty_book(monkeypatch, tmp_path):
    from xsource.cli import cockpit as cockpit_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    monkeypatch.setattr(cockpit_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = cockpit_mod._book_publish_preview_step(_ctx([]), {})
    assert result.ok is False
    assert result.message == "No suppliers in the black book."
