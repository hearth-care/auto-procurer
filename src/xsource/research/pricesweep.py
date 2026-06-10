"""Indicative price range for a job type."""

from __future__ import annotations

import logging

log = logging.getLogger("xsource.research")

PRICE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "low_gbp": {"type": ["number", "null"]},
        "high_gbp": {"type": ["number", "null"]},
        "source_count": {"type": "integer"},
        "note": {"type": "string"},
    },
    "required": ["low_gbp", "high_gbp", "source_count", "note"],
}


def sweep_prices(job_term: str, region: str, searcher) -> dict | None:
    query = f"typical cost {job_term} {region} UK 2026"
    try:
        raw = searcher.extract(query, PRICE_SCHEMA)
    except Exception as exc:
        log.warning("price sweep failed: %s", exc)
        return None
    low, high, sources = raw.get("low_gbp"), raw.get("high_gbp"), raw.get("source_count", 0)
    if low is None or high is None or sources < 1:
        return None
    return {
        "low": int(low),
        "high": int(high),
        "sources": int(sources),
        "note": raw.get("note", ""),
    }
