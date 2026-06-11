"""Monthly research-spend meter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xsource.store.files import SyncedFile


class Budget:
    def __init__(
        self, state_dir: Path, monthly_cap_gbp: float, month: str, blob: Any | None = None
    ):
        self.cap = monthly_cap_gbp
        self.path = Path(state_dir) / f"budget-{month}.json"
        self._synced = SyncedFile(self.path, blob=blob)
        self._synced.hydrate()

    def spent(self) -> float:
        if not self.path.exists():
            return 0.0
        return round(float(json.loads(self.path.read_text())["spent_gbp"]), 2)

    def record(self, amount_gbp: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"spent_gbp": round(self.spent() + amount_gbp, 4)}))
        self._synced.upload()

    def level(self) -> str:
        frac = self.spent() / self.cap if self.cap else 1.0
        return "blocked" if frac >= 1.0 else ("warn" if frac >= 0.75 else "ok")

    def allow_new_run(self) -> bool:
        return self.level() != "blocked"
