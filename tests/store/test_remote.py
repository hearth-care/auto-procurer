from xsource.config import Config
from xsource.store.models import InvoiceRecord, Supplier
from xsource.store.remote import SyncedStore
from xsource.wiring import build_stores


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


def test_build_stores_includes_invoice_store(tmp_path, monkeypatch):
    monkeypatch.setattr("xsource.wiring.make_blob", lambda bucket, path: None)
    cfg = Config(
        home_postcode=None,
        default_radius_miles=15,
        shortlist_n=5,
        max_places_calls=10,
        max_web_searches=8,
        monthly_budget_gbp=10.0,
        chase_after_days=3,
        poll_seconds=60,
        drive_folder_id=None,
        staff_share_group=None,
        state_dir=str(tmp_path),
    )
    suppliers, requests, invoices = build_stores(cfg)

    assert suppliers.path.name == "suppliers.jsonl"
    assert requests.path.name == "requests.jsonl"
    assert invoices.path.name == "invoices.jsonl"
    assert invoices._store.model is InvoiceRecord
