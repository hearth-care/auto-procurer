from xsource.research.pricesweep import PRICE_SCHEMA, sweep_prices


class FakeSearcher:
    def __init__(self, payload):
        self.payload, self.queries = payload, []

    def extract(self, query, schema):
        self.queries.append(query)
        assert schema is PRICE_SCHEMA
        return self.payload


def test_price_range_with_sources():
    searcher = FakeSearcher(
        {
            "low_gbp": 150,
            "high_gbp": 400,
            "source_count": 3,
            "note": "regional typical for tree removal",
        }
    )
    result = sweep_prices("tree removal", "Devon", searcher=searcher)
    assert result == {
        "low": 150,
        "high": 400,
        "sources": 3,
        "note": "regional typical for tree removal",
    }


def test_no_data_returns_none_never_invented():
    searcher = FakeSearcher({"low_gbp": None, "high_gbp": None, "source_count": 0, "note": ""})
    assert sweep_prices("obscure thing", "Devon", searcher=searcher) is None


def test_failure_degrades_to_none():
    class Boom:
        def extract(self, query, schema):
            raise RuntimeError("down")

    assert sweep_prices("x", "Devon", searcher=Boom()) is None
