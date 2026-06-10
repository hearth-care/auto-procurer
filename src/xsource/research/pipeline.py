"""The staged research run, pure of UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from xsource.research.candidates import Candidate
from xsource.research.rank import dedupe, rank
from xsource.research.triage import Triage

log = logging.getLogger("xsource.research")

DIRECTORY_SITES = ["yell.com", "checkatrade.com"]


@dataclass
class RunCaps:
    max_places: int
    max_web: int
    places_used: int = 0
    web_used: int = 0

    def take_places(self) -> bool:
        if self.places_used >= self.max_places:
            return False
        self.places_used += 1
        return True

    def take_web(self) -> bool:
        if self.web_used >= self.max_web:
            return False
        self.web_used += 1
        return True


@dataclass
class ResearchResult:
    shortlist: list[Candidate]
    indicative: dict | None
    stages: dict[str, str]
    caps: RunCaps = field(default_factory=lambda: RunCaps(0, 0))


def _stage(stages: dict, name: str, fn, default):
    try:
        out = fn()
        stages[name] = stages.get(name) or "ok"
        return out
    except Exception as exc:
        log.warning("stage %s failed: %s", name, exc)
        stages[name] = "skipped"
        return default


def run_research(
    triage: Triage,
    book_matches: list[Candidate],
    places_fn,
    directory_fn,
    price_fn,
    ch_fn,
    caps: RunCaps,
    shortlist_n: int,
) -> ResearchResult:
    stages: dict[str, str] = {"black book": "ok"}
    candidates: list[Candidate] = list(book_matches)

    def places():
        out = []
        for term in triage.search_terms + triage.also_try:
            if not caps.take_places():
                stages["places"] = "capped"
                break
            out.extend(places_fn(term))
        return out

    candidates += _stage(stages, "places", places, [])

    def directories():
        out = []
        for site in DIRECTORY_SITES:
            if not caps.take_web():
                stages["directories"] = "capped"
                break
            out.extend(directory_fn(triage.search_terms[0], site))
        return out

    candidates += _stage(stages, "directories", directories, [])

    if caps.take_web():
        indicative = _stage(stages, "web sweep", lambda: price_fn(triage.search_terms[0]), None)
    else:
        stages["web sweep"] = "capped"
        indicative = None

    shortlist = rank(dedupe(candidates), shortlist_n)

    def cross_check():
        for candidate in shortlist:
            info = ch_fn(candidate.name)
            if info:
                candidate.extra = candidate.extra or {}
                candidate.extra["companies_house"] = info
        return None

    _stage(stages, "rank & dedupe", cross_check, None)
    return ResearchResult(shortlist=shortlist, indicative=indicative, stages=stages, caps=caps)
