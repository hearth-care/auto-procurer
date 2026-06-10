from xsource.research.candidates import Candidate
from xsource.research.rank import dedupe, rank


def C(**kw):
    return Candidate(**{"name": "X", "source": "places", **kw})


def test_dedupe_merges_by_phone_keeping_all_provenance():
    a = C(
        name="TQ Tree Services",
        phone="+441626870111",
        rating=4.8,
        review_count=57,
        rating_scale=5,
        source="places",
        source_url="maps://1",
    )
    b = C(
        name="T Q Tree Services Ltd",
        phone="+441626870111",
        rating=4.5,
        review_count=3,
        rating_scale=5,
        source="yell",
        source_url="https://yell.com/biz/tq",
    )
    merged = dedupe([a, b])
    assert len(merged) == 1
    merged_candidate = merged[0]
    assert merged_candidate.name == "TQ Tree Services"
    assert merged_candidate.extra["also"] == [
        {
            "source": "yell",
            "source_url": "https://yell.com/biz/tq",
            "rating": 4.5,
            "review_count": 3,
            "rating_scale": 5,
        }
    ]


def test_dedupe_merges_by_website_domain():
    a = C(name="A", website="tqtrees.co.uk", source="places")
    b = C(name="A Trading", website="tqtrees.co.uk", source="web")
    assert len(dedupe([a, b])) == 1


def test_dedupe_merges_by_fuzzy_name():
    a = C(name="Westcountry Tree Care")
    b = C(name="westcountry tree care ltd", source="yell", source_url="u")
    assert len(dedupe([a, b])) == 1


def test_distinct_candidates_survive():
    assert len(dedupe([C(name="A", phone="+441000000001"), C(name="B", phone="+441000000002")])) == 2


def test_rank_book_first_then_rating_volume():
    book = C(name="Westcountry", source="book", rating=4.9, review_count=31, rating_scale=5)
    big = C(name="Big", rating=4.8, review_count=57, rating_scale=5)
    small = C(name="Small", rating=4.9, review_count=2, rating_scale=5)
    none = C(name="NoRating")
    ranked = rank([none, small, big, book], shortlist_n=4)
    assert [c.name for c in ranked] == ["Westcountry", "Big", "Small", "NoRating"]


def test_rank_normalises_checkatrade_scale():
    chk = C(name="Chk", source="checkatrade", rating=9.4, review_count=12, rating_scale=10)
    goog = C(name="Goog", rating=4.2, review_count=12, rating_scale=5)
    assert [c.name for c in rank([goog, chk], shortlist_n=2)] == ["Chk", "Goog"]


def test_rank_truncates_to_n():
    cands = [C(name=f"c{i}", rating=4.0, review_count=i, rating_scale=5) for i in range(10)]
    assert len(rank(cands, shortlist_n=5)) == 5
