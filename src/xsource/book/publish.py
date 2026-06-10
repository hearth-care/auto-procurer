"""Read-only staff directory sheet values."""

from __future__ import annotations

from xsource.store.models import Supplier

_HEAD = ["Name", "Categories", "Phone", "Email", "Preferred", "Last used", "Last price", "Notes"]


def build_directory_values(suppliers: list[Supplier]) -> list[list[str]]:
    rows = [list(_HEAD)]
    for supplier in sorted(suppliers, key=lambda item: item.name.lower()):
        last_price = "—"
        if supplier.price_history:
            price = supplier.price_history[-1]
            last_price = f"£{price['amount']} ({price['job']})"
        last_note = supplier.notes[-1]["text"] if supplier.notes else "—"
        rows.append(
            [
                supplier.name,
                ", ".join(supplier.categories) or "—",
                supplier.phone or "—",
                supplier.email or "—",
                "yes" if supplier.preferred else "",
                supplier.last_used or "—",
                last_price,
                last_note,
            ]
        )
    return rows
