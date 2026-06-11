from __future__ import annotations

from xsource.store.files import SyncedFile


class _Blob:
    def __init__(self, body: bytes | None = None) -> None:
        self.body = body
        self.uploads: list[bytes] = []

    def exists(self) -> bool:
        return self.body is not None

    def download_as_bytes(self) -> bytes:
        assert self.body is not None
        return self.body

    def upload_from_filename(self, filename: str) -> None:
        with open(filename, "rb") as handle:
            data = handle.read()
        self.body = data
        self.uploads.append(data)


def test_synced_file_downloads_existing_blob_and_uploads_after_context(tmp_path) -> None:
    blob = _Blob(b"existing")
    path = tmp_path / "watcher.sqlite3"

    with SyncedFile(path, blob=blob) as synced:
        assert synced.path.read_bytes() == b"existing"
        synced.path.write_bytes(b"updated")

    assert blob.uploads == [b"updated"]


def test_synced_file_without_blob_uses_local_file_only(tmp_path) -> None:
    path = tmp_path / "budget-2026-06.json"

    with SyncedFile(path, blob=None) as synced:
        synced.path.write_text('{"spent_gbp": 1.25}')

    assert path.read_text() == '{"spent_gbp": 1.25}'
