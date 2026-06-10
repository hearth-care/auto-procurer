"""Canonical records for the xsource store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


def _filtered(cls, d: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in names}


@dataclass
class Supplier:
    id: str
    name: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None
    postcode: str | None = None
    place_id: str | None = None
    rating: dict[str, Any] = field(default_factory=dict)
    source: str = "manual"
    source_url: str | None = None
    companies_house: dict[str, Any] | None = None
    preferred: bool = False
    preferred_set: str | None = None
    first_seen: str | None = None
    last_used: str | None = None
    price_history: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    recurs_every_months: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Supplier:
        return cls(**_filtered(cls, d))


@dataclass
class ShortlistEntry:
    supplier_id: str
    rank: int
    indicative: list[int] | None = None
    outreach: dict[str, Any] = field(default_factory=dict)
    reply: dict[str, Any] = field(default_factory=dict)
    excluded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ShortlistEntry:
        return cls(**_filtered(cls, d))


@dataclass
class Request:
    id: str
    created_at: str
    raw_need: str
    triage: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    status: str = "open"
    sheet_id: str | None = None
    sheet_url: str | None = None
    indicative_range: dict[str, Any] | None = None
    shortlist: list[ShortlistEntry] = field(default_factory=list)
    chosen_supplier_id: str | None = None
    watcher: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["shortlist"] = [
            e.to_dict() if isinstance(e, ShortlistEntry) else e for e in self.shortlist
        ]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Request:
        filtered = dict(_filtered(cls, d))
        filtered["shortlist"] = [
            ShortlistEntry.from_dict(e) for e in filtered.get("shortlist", [])
        ]
        return cls(**filtered)
