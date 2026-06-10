import pytest

from xsource.research.triage import Triage, TriageError, run_triage

GOOD = {
    "category": "trees-grounds",
    "search_terms": ["tree surgeon", "tree removal"],
    "also_try": ["chipper hire"],
    "email_vars": {"job_summary": "fallen tree, cut/chip/remove", "location_town": "Newton Abbot"},
}


class FakeGateway:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_structured(self, messages, schema, role="research"):
        self.calls += 1
        return self.payload


def test_good_triage_parses():
    t = run_triage("tree down", {"radius_miles": 15}, FakeGateway(GOOD))
    assert isinstance(t, Triage)
    assert t.category == "trees-grounds" and t.search_terms == ["tree surgeon", "tree removal"]


def test_missing_field_raises_clean_error():
    bad = {k: v for k, v in GOOD.items() if k != "search_terms"}
    with pytest.raises(TriageError):
        run_triage("tree down", {}, FakeGateway(bad))


def test_empty_search_terms_rejected():
    with pytest.raises(TriageError):
        run_triage("tree down", {}, FakeGateway({**GOOD, "search_terms": []}))
