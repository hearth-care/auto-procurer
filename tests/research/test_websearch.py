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


# --- AnthropicSearcher fallback chain tests ---


class _OverloadedError(Exception):
    pass


class _AuthError(Exception):
    pass


def _make_searcher(model_chain, side_effects):
    from xsource.research.websearch import AnthropicSearcher

    searcher = object.__new__(AnthropicSearcher)
    searcher.model_chain = list(model_chain)
    call_log = []

    def _extract_with_model(model, query, schema):
        call_log.append(model)
        exc = side_effects.get(model)
        if exc is not None:
            raise exc
        return {"candidates": []}

    searcher._extract_with_model = _extract_with_model  # type: ignore[method-assign]
    return searcher, call_log


def test_searcher_fallback_emits_obs_event(monkeypatch):
    import xsource.research.websearch as ws_mod

    monkeypatch.setattr(
        ws_mod, "_is_retriable_error", lambda exc: isinstance(exc, _OverloadedError)
    )
    events = []
    monkeypatch.setattr("xsource.obs.event", lambda name, **kw: events.append(name))

    searcher, calls = _make_searcher(
        ["model-a", "model-b"],
        {"model-a": _OverloadedError("overloaded")},
    )
    result = searcher.extract("query", {})
    assert result == {"candidates": []}
    assert calls == ["model-a", "model-b"]
    assert "gateway.model_fallback" in events


def test_searcher_no_fallback_on_non_retriable(monkeypatch):
    import xsource.research.websearch as ws_mod

    monkeypatch.setattr(
        ws_mod, "_is_retriable_error", lambda exc: isinstance(exc, _OverloadedError)
    )
    events = []
    monkeypatch.setattr("xsource.obs.event", lambda name, **kw: events.append(name))

    searcher, calls = _make_searcher(
        ["model-a", "model-b"],
        {"model-a": _AuthError("bad key")},
    )
    import pytest

    with pytest.raises(_AuthError):
        searcher.extract("query", {})
    assert calls == ["model-a"]
    assert "gateway.model_fallback" not in events
