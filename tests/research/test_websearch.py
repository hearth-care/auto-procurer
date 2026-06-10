from xsource.research.websearch import DIRECTORY_SCHEMA, search_directory


class FakeSearcher:
    def __init__(self, payload):
        self.payload, self.queries = payload, []

    def extract(self, query: str, schema: dict) -> dict:
        self.queries.append(query)
        assert schema is DIRECTORY_SCHEMA
        return self.payload


def test_search_directory_validates_and_filters():
    payload = {
        "candidates": [
            {
                "name": "Good Trade",
                "profile_url": "https://www.yell.com/biz/good-1/",
                "phone": "01626 870999",
                "rating": 4.5,
                "review_count": 3,
                "email": None,
                "town": "Newton Abbot",
                "categories": ["tree surgery"],
                "source_quote": "4.5 (3 reviews)",
            },
            {
                "name": "Bad Provenance",
                "profile_url": "https://elsewhere.com/x",
                "phone": None,
                "rating": 5,
                "review_count": 1,
                "email": None,
                "town": None,
                "categories": [],
                "source_quote": "x",
            },
        ]
    }
    searcher = FakeSearcher(payload)
    cands = search_directory("tree surgeon", "Newton Abbot", "yell.com", searcher=searcher)
    assert [c.name for c in cands] == ["Good Trade"]
    assert searcher.queries == ["site:yell.com tree surgeon Newton Abbot"]


def test_searcher_failure_returns_empty_and_does_not_raise():
    class Boom:
        def extract(self, query, schema):
            raise RuntimeError("api down")

    assert search_directory("x", "Y", "yell.com", searcher=Boom()) == []
