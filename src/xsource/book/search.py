"""Black-book matching."""

from __future__ import annotations

from xsource.store.models import Supplier


def find_matches(suppliers: list[Supplier], category: str, tags: list[str]) -> list[Supplier]:
    out = []
    for supplier in suppliers:
        if category in supplier.categories or (tags and set(tags) & set(supplier.tags)):
            out.append(supplier)
    return out


def search_suppliers(suppliers: list[Supplier], term: str) -> list[Supplier]:
    needle = term.lower().strip()
    return [
        supplier
        for supplier in suppliers
        if needle in supplier.name.lower()
        or any(needle in category for category in supplier.categories)
        or any(needle in tag for tag in supplier.tags)
    ]


def format_supplier_row(supplier: Supplier) -> str:
    return (
        f"{supplier.id}\t{supplier.name}\t{','.join(supplier.categories)}\t"
        f"{','.join(supplier.tags)}\t{supplier.phone or ''}"
    )
