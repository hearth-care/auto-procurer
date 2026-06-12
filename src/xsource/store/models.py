"""Canonical records for the xsource store."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field, fields
from typing import Any


def _filtered(cls, d: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in names}


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


class InvoiceTransitionError(ValueError):
    pass


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
        filtered["shortlist"] = [ShortlistEntry.from_dict(e) for e in filtered.get("shortlist", [])]
        return cls(**filtered)


@dataclass
class InvoiceRecord:
    id: str
    request_id: str
    supplier_id: str
    amount_minor: int
    invoice_date: str
    description: str
    source: str
    currency: str = "GBP"
    invoice_number: str | None = None
    due_date: str | None = None
    file_ref: str | None = None
    status: str = "captured"
    handoff: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    _TRANSITIONS = {
        "captured": {"emitted"},
        "emitted": {"acknowledged", "rejected"},
        "acknowledged": {"settled", "disputed"},
        "disputed": {"re-emitted", "settled", "written_off"},
        "re-emitted": {"acknowledged", "rejected"},
        "rejected": {"emitted", "written_off"},
        "settled": set(),
        "written_off": set(),
    }

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be an integer minor-unit amount")
        if self.status not in self._TRANSITIONS:
            raise InvoiceTransitionError(f"unknown invoice status: {self.status}")

    def transition_to(self, status: str, *, at: str | None = None) -> None:
        allowed = self._TRANSITIONS.get(self.status, set())
        if status not in allowed:
            raise InvoiceTransitionError(
                f"cannot transition invoice {self.id} {self.status}->{status}"
            )
        self.status = status
        self.updated_at = at or _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InvoiceRecord:
        return cls(**_filtered(cls, d))
