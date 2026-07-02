from xsource.book.importer import import_csv
from xsource.research.phones import normalise_uk_phone
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Supplier

CSV = """name,category,tags,phone,email,notes
Westcountry Tree Care,trees-grounds,tree-surgery;chipping,01626 332000,info@wtc.co.uk,fast and tidy
Smith Heating,heating,boiler,07700 900123,,
"""

DUPLICATE_CSV = """name,category,tags,phone,email,notes
Gamma Roofing,roofing,slate,01632 960100,,
gamma roofing,roofing,flat-roof,01632 960101,,
"""


def test_import_creates_suppliers(tmp_path):
    f = tmp_path / "book.csv"
    f.write_text(CSV)
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    report = import_csv(f, store, today="2026-06-10")
    assert report == {"imported": 2, "skipped": 0}
    supplier = store.all()[0]
    assert supplier.id == "s-0001" and supplier.source == "import"
    assert supplier.phone == "+441626332000"
    assert supplier.tags == ["tree-surgery", "chipping"]
    assert supplier.notes[0]["text"] == "fast and tidy"


def test_reimport_skips_existing_by_name(tmp_path):
    f = tmp_path / "book.csv"
    f.write_text(CSV)
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    import_csv(f, store, today="2026-06-10")
    report = import_csv(f, store, today="2026-06-10")
    assert report == {"imported": 0, "skipped": 2}


def test_import_dry_run_matches_wet_report(tmp_path):
    f = tmp_path / "book.csv"
    f.write_text(CSV)
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    dry = import_csv(f, store, today="2026-06-10", dry_run=True)
    assert dry == {"imported": 2, "skipped": 0}
    assert store.all() == []
    wet = import_csv(f, store, today="2026-06-10")
    assert wet == dry


def test_import_intra_csv_duplicate_skipped(tmp_path):
    f = tmp_path / "book.csv"
    f.write_text(DUPLICATE_CSV)
    store = JsonlStore(tmp_path / "suppliers.jsonl", Supplier)
    report = import_csv(f, store, today="2026-06-10")
    assert report == {"imported": 1, "skipped": 1}
    assert [s.name for s in store.all()] == ["Gamma Roofing"]


def test_phone_normalisation():
    assert normalise_uk_phone("01626 332000") == "+441626332000"
    assert normalise_uk_phone("+44 7700 900123") == "+447700900123"
    assert normalise_uk_phone("07700 900123") == "+447700900123"
    assert normalise_uk_phone("not a phone") is None
    assert normalise_uk_phone("") is None
