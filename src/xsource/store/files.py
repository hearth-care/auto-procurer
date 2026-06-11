"""Blob-synced local files for Cloud Run scratch state."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SyncedFile:
    def __init__(self, path: Path, *, blob: Any | None) -> None:
        self.path = Path(path)
        self.blob = blob

    def hydrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.blob is not None and self.blob.exists():
            self.path.write_bytes(self.blob.download_as_bytes())

    def upload(self) -> None:
        if self.blob is not None and self.path.exists():
            self.blob.upload_from_filename(str(self.path))

    def __enter__(self) -> SyncedFile:
        self.hydrate()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.upload()
