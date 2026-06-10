"""The one shape every discovery source emits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    name: str
    source: str
    source_url: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None
    postcode: str | None = None
    place_id: str | None = None
    rating: float | None = None
    review_count: int | None = None
    rating_scale: int | None = None
    extra: dict | None = None
