from xsource.research.candidates import Candidate
from xsource.research.pipeline import RunCaps, run_research
from xsource.research.triage import Triage

TRIAGE = Triage(
    category="trees-grounds",
    search_terms=["tree surgeon"],
    also_try=[],
    email_vars={"job_summary": "x", "location_town": "Newton Abbot"},
)


def test_pipeline_merges_sources_and_respects_caps():
    calls = {"places": 0, "dir": 0}

    def places_fn(term):
        calls["places"] += 1
        return [Candidate(name="From Places", source="places", phone="+441626000001")]

    def dir_fn(term, site):
        calls["dir"] += 1
        return [
            Candidate(
                name=f"From {site}",
                source="yell" if "yell" in site else "checkatrade",
                source_url=f"https://{site}/x",
            )
        ]

    result = run_research(
        triage=TRIAGE,
        book_matches=[],
        places_fn=places_fn,
        directory_fn=dir_fn,
        price_fn=lambda term: {"low": 100, "high": 300, "sources": 2, "note": ""},
        ch_fn=lambda name: None,
        caps=RunCaps(max_places=10, max_web=8),
        shortlist_n=5,
    )
    assert calls["places"] == 1 and calls["dir"] == 2
    assert {c.name for c in result.shortlist} == {
        "From Places",
        "From yell.com",
        "From checkatrade.com",
    }
    assert result.indicative == {"low": 100, "high": 300, "sources": 2, "note": ""}
    assert result.stages["places"] == "ok" and result.stages["directories"] == "ok"


def test_caps_block_excess_calls():
    def places_fn(term):
        places_fn.n += 1
        return []

    places_fn.n = 0
    triage = Triage(
        category="c",
        search_terms=["a", "b", "c"],
        also_try=["d", "e"],
        email_vars={"job_summary": "x", "location_town": "T"},
    )
    run_research(
        triage,
        [],
        places_fn,
        lambda *a: [],
        lambda *a: None,
        lambda *a: None,
        caps=RunCaps(max_places=2, max_web=0),
        shortlist_n=5,
    )
    assert places_fn.n == 2


def test_failed_stage_is_skipped_run_completes():
    def boom(term):
        raise RuntimeError("api down")

    result = run_research(
        TRIAGE,
        [],
        boom,
        lambda *a: [],
        lambda *a: None,
        lambda *a: None,
        caps=RunCaps(max_places=5, max_web=5),
        shortlist_n=5,
    )
    assert result.stages["places"] == "skipped"
    assert result.shortlist == []


def test_book_matches_rank_first():
    book = Candidate(name="Old Friend", source="book", rating=4.9, review_count=31, rating_scale=5)

    def places_fn(term):
        return [
            Candidate(
                name="Shiny New", source="places", rating=4.9, review_count=500, rating_scale=5
            )
        ]

    result = run_research(
        TRIAGE,
        [book],
        places_fn,
        lambda *a: [],
        lambda *a: None,
        lambda *a: None,
        caps=RunCaps(max_places=5, max_web=5),
        shortlist_n=5,
    )
    assert result.shortlist[0].name == "Old Friend"
