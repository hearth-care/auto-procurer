from xsource.book.importer import import_csv
from xsource.research.phones import normalise_uk_phone
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Supplier

CSV = """name,category,tags,phone,email,notes
Westcountry Tree Care,trees-grounds,tree-surgery;chipping,01626 332000,info@wtc.co.uk,fast and tidy
Smith Heating,heating,boiler,07700 900123,,
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


def test_phone_normalisation():
    assert normalise_uk_phone("01626 332000") == "+441626332000"
    assert normalise_uk_phone("+44 7700 900123") == "+447700900123"
    assert normalise_uk_phone("07700 900123") == "+447700900123"
    assert normalise_uk_phone("not a phone") is None
    assert normalise_uk_phone("") is None
