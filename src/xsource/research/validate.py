"""Deterministic gate between LLM extraction and the shortlist."""

from __future__ import annotations

from urllib.parse import urlparse

from xsource.research.candidates import Candidate
from xsource.research.phones import normalise_uk_phone

_SITE_META = {
    "yell.com": ("yell", 5.0),
    "checkatrade.com": ("checkatrade", 10.0),
}


def validate_directory_candidate(raw: dict, site: str) -> Candidate | None:
    source, scale = _SITE_META[site]
    url = raw.get("profile_url")
    if not url or not urlparse(url).netloc.lower().endswith(site):
        return None
    name = (raw.get("name") or "").strip()
    if not name:
        return None
    rating, count = raw.get("rating"), raw.get("review_count")
    if not isinstance(rating, int | float) or not (0 <= float(rating) <= scale):
        rating, count = None, None
    return Candidate(
        name=name,
        source=source,
        source_url=url,
        phone=normalise_uk_phone(raw.get("phone") or ""),
        email=(raw.get("email") or "").strip() or None,
        rating=float(rating) if rating is not None else None,
        review_count=int(count) if isinstance(count, int) else None,
        rating_scale=int(scale) if rating is not None else None,
    )
