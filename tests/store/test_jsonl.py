import json

from xsource.store.jsonl import JsonlStore
from xsource.store.models import Supplier


def make_store(tmp_path):
    return JsonlStore(path=tmp_path / "suppliers.jsonl", model=Supplier)


def test_empty_store_loads_empty(tmp_path):
    assert make_store(tmp_path).all() == []


def test_upsert_and_reload_identical(tmp_path):
    st = make_store(tmp_path)
    st.upsert(Supplier(id="s-1", name="A"))
    st.upsert(Supplier(id="s-2", name="B"))
    st.upsert(Supplier(id="s-1", name="A renamed"))
    reloaded = make_store(tmp_path)
    assert [x.name for x in reloaded.all()] == ["A renamed", "B"]
    assert reloaded.get("s-1").name == "A renamed"


def test_corrupt_line_is_quarantined_not_fatal(tmp_path, capsys):
    p = tmp_path / "suppliers.jsonl"
    p.write_text(json.dumps({"id": "s-1", "name": "ok"}) + "\n{BROKEN\n")
    st = make_store(tmp_path)
    assert [x.id for x in st.all()] == ["s-1"]
    quarantine = tmp_path / "suppliers.jsonl.quarantine"
    assert quarantine.exists() and "{BROKEN" in quarantine.read_text()
