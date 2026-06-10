from xsource.store.models import Supplier
from xsource.store.remote import SyncedStore


class FakeBlob:
    def __init__(self):
        self.data = None
        self.exists_flag = False

    def exists(self):
        return self.exists_flag

    def download_as_text(self):
        return self.data

    def upload_from_filename(self, path):
        with open(path) as f:
            self.data = f.read()
        self.exists_flag = True


def test_offline_degrades_to_local_readonly(tmp_path):
    store = SyncedStore(local_dir=tmp_path, filename="suppliers.jsonl", model=Supplier, blob=None)
    assert store.offline is True and store.all() == []


def test_pull_then_upsert_pushes(tmp_path):
    blob = FakeBlob()
    store = SyncedStore(tmp_path, "suppliers.jsonl", Supplier, blob)
    store.upsert(Supplier(id="s-1", name="A"))
    assert '"s-1"' in blob.data
    other = SyncedStore(tmp_path / "other", "suppliers.jsonl", Supplier, blob)
    assert other.get("s-1").name == "A"
