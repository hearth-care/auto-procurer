from typer.testing import CliRunner

from xsource.cli import app
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Supplier

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
