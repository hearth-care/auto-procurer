"""CSV seed import for the owner's existing black book."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

from xsource.research.phones import normalise_uk_phone
from xsource.store.models import Supplier


class SupplierStore(Protocol):
    def all(self) -> list[Supplier]: ...

    def upsert(self, rec: Supplier) -> None: ...

    def next_id(self, prefix: str) -> str: ...


def import_csv(
    path: Path, store: SupplierStore, today: str, *, dry_run: bool = False
) -> dict[str, int]:
    existing = {supplier.name.lower() for supplier in store.all()}
    imported = skipped = 0
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            if name.lower() in existing:
                skipped += 1
                continue
            notes = (
                [{"date": today, "by": "import", "text": row["notes"].strip()}]
                if (row.get("notes") or "").strip()
                else []
            )
            if not dry_run:
                store.upsert(
                    Supplier(
                        id=store.next_id("s"),
                        name=name,
                        categories=[c for c in [(row.get("category") or "").strip()] if c],
                        tags=[
                            t.strip() for t in (row.get("tags") or "").split(";") if t.strip()
                        ],
                        phone=normalise_uk_phone(row.get("phone") or ""),
                        email=(row.get("email") or "").strip() or None,
                        source="import",
                        first_seen=today,
                        notes=notes,
                    )
                )
            existing.add(name.lower())
            imported += 1
    return {"imported": imported, "skipped": skipped}
