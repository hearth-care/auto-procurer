"""Merge and order candidates."""

from __future__ import annotations

import math
import re

from xsource.research.candidates import Candidate


def _name_key(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]", "", name.lower())
    normalized = re.sub(r"\b(ltd|limited|services|service)\b", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _keys(candidate: Candidate):
    if candidate.phone:
        yield ("phone", candidate.phone)
    if candidate.website:
        yield ("site", candidate.website)
    yield ("name", _name_key(candidate.name))


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen: dict[tuple, Candidate] = {}
    out: list[Candidate] = []
    for candidate in cands:
        hit = next((seen[key] for key in _keys(candidate) if key in seen), None)
        if hit is None:
            out.append(candidate)
            for key in _keys(candidate):
                seen[key] = candidate
            continue
        hit.extra = hit.extra or {}
        hit.extra.setdefault("also", []).append(
            {
                "source": candidate.source,
                "source_url": candidate.source_url,
                "rating": candidate.rating,
                "review_count": candidate.review_count,
                "rating_scale": candidate.rating_scale,
            }
        )
        for field in ("phone", "email", "website", "address", "postcode"):
            if getattr(hit, field) is None and getattr(candidate, field) is not None:
                setattr(hit, field, getattr(candidate, field))
    return out


def _score(candidate: Candidate) -> float:
    book_boost = 100.0 if candidate.source == "book" else 0.0
    if candidate.rating is None or not candidate.rating_scale:
        return book_boost
    normalised = candidate.rating * (5.0 / candidate.rating_scale)
    volume = math.log1p(candidate.review_count or 0)
    return book_boost + normalised * (1.0 + volume)


def rank(cands: list[Candidate], shortlist_n: int) -> list[Candidate]:
    return sorted(cands, key=_score, reverse=True)[:shortlist_n]
