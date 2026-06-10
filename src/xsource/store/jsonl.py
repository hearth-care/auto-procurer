"""Whole-file JSONL store with corrupt-line quarantine."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("xsource.store")


class JsonlStore:
    def __init__(self, path: Path, model: type[Any]):
        self.path = Path(path)
        self.model = model
        self._records: dict[str, object] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = self.model.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError) as exc:
                log.warning("quarantining corrupt line in %s: %s", self.path.name, exc)
                with open(f"{self.path}.quarantine", "a") as q:
                    q.write(line + "\n")
                continue
            self._records[rec.id] = rec

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            for rec in self._records.values():
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)

    def all(self) -> list:
        return list(self._records.values())

    def get(self, rec_id: str):
        return self._records.get(rec_id)

    def upsert(self, rec) -> None:
        self._records[rec.id] = rec
        self._flush()

    def next_id(self, prefix: str) -> str:
        nums = [
            int(r.id.split("-", 1)[1])
            for r in self._records.values()
            if r.id.startswith(f"{prefix}-") and r.id.split("-", 1)[1].isdigit()
        ]
        return f"{prefix}-{(max(nums) + 1 if nums else 1):04d}"
