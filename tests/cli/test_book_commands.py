from typer.testing import CliRunner

from xsource.cli import app
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Supplier
from xsource.store.remote import StoreOffline

runner = CliRunner()

_CSV = """name,category,tags,phone,email,notes
Gamma Roofing,roofing,slate;flat-roof,01632 960100,gamma@example.com,synthetic seed row
Beta Heating,heating,boiler,01632 960101,,
"""


def _seeded_suppliers(tmp_path):
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
    store.upsert(
        Supplier(
            id="s-0002",
            name="Beta Heating",
            categories=["heating"],
            tags=["boiler"],
        )
    )
    return store


def test_book_search_prints_pinned_row(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    store = _seeded_suppliers(tmp_path)
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = runner.invoke(app, ["book", "search", "heating"])
    assert result.exit_code == 0
    assert result.stdout == "s-0002\tBeta Heating\theating\tboiler\t\n"


def test_book_search_no_matches_prints_nothing(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    store = _seeded_suppliers(tmp_path)
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = runner.invoke(app, ["book", "search", "roofing"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_book_search_warns_on_quarantine(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    path = tmp_path / "suppliers.jsonl"
    path.write_text(
        '{"id": "s-0001", "name": "Alpha Tree Care", "categories": ["trees-grounds"], '
        '"tags": ["tree-surgery"]}\n'
        "not json\n"
    )
    store = JsonlStore(path, Supplier)
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = runner.invoke(app, ["book", "search", "alpha"])
    assert result.exit_code == 0
    assert "warning: 1 corrupt line(s) quarantined in suppliers.jsonl" in result.stderr


def test_book_import_reports_and_writes(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    store.upsert(Supplier(id="s-0002", name="Beta Heating"))
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = runner.invoke(app, ["book", "import", str(csv_file)])
    assert result.exit_code == 0
    assert "{'imported': 1, 'skipped': 1}" in result.stdout
    assert {s.name for s in store.all()} == {"Beta Heating", "Gamma Roofing"}


def test_book_import_dry_run_writes_nothing(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    store.upsert(Supplier(id="s-0002", name="Beta Heating"))
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = runner.invoke(app, ["book", "import", str(csv_file), "--dry-run"])
    assert result.exit_code == 0
    assert "{'imported': 1, 'skipped': 1}" in result.stdout
    assert [s.name for s in store.all()] == ["Beta Heating"]


def test_book_import_missing_file_exits_2(tmp_path):
    result = runner.invoke(app, ["book", "import", str(tmp_path / "absent.csv")])
    assert result.exit_code == 2


def test_book_import_header_only_csv(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    csv_file = tmp_path / "book.csv"
    csv_file.write_text("name,category,tags,phone,email,notes\n")
    result = runner.invoke(app, ["book", "import", str(csv_file)])
    assert result.exit_code == 0
    assert "{'imported': 0, 'skipped': 0}" in result.stdout


def test_book_import_store_offline_exits_1(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    class _OfflineStore:
        path = tmp_path / "suppliers.jsonl"
        quarantined = 0

        def all(self):
            return []

        def next_id(self, prefix):
            return "s-0001"

        def upsert(self, rec):
            raise StoreOffline("store is offline (read-only local cache)")

    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (_OfflineStore(), object(), object()))
    csv_file = tmp_path / "book.csv"
    csv_file.write_text(_CSV)
    result = runner.invoke(app, ["book", "import", str(csv_file)])
    assert result.exit_code == 1
    assert "store offline: store is offline (read-only local cache)" in result.stderr


def test_book_publish_cli_empty_book(monkeypatch, tmp_path):
    from xsource.cli import book as book_mod

    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    monkeypatch.setattr(book_mod, "build_stores", lambda cfg: (store, object(), object()))
    result = runner.invoke(app, ["book", "publish"])
    assert result.exit_code == 1
    assert "no suppliers to publish" in result.stderr
