"""GCS-synced JSONL store."""

from __future__ import annotations

from pathlib import Path

from xsource.store.jsonl import JsonlStore


class StoreOffline(RuntimeError):
    pass


class SyncedStore:
    def __init__(self, local_dir: Path, filename: str, model, blob):
        self.blob = blob
        self.offline = blob is None
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        self.path = local_dir / filename
        if blob is not None and blob.exists():
            self.path.write_text(blob.download_as_text())
        self._store = JsonlStore(self.path, model)

    def all(self):
        return self._store.all()

    def get(self, rec_id: str):
        return self._store.get(rec_id)

    def next_id(self, prefix: str) -> str:
        return self._store.next_id(prefix)

    def upsert(self, rec) -> None:
        if self.offline:
            raise StoreOffline("store is offline (read-only local cache)")
        self._store.upsert(rec)
        self.blob.upload_from_filename(str(self.path))


def make_blob(bucket_name: str, blob_path: str):
    try:
        from google.cloud import storage

        return storage.Client().bucket(bucket_name).blob(blob_path)
    except Exception:
        return None
