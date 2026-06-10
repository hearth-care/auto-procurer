import datetime as dt

from xsource.research.candidates import Candidate
from xsource.research.pipeline import ResearchResult, RunCaps
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Request, Supplier
from xsource.walks.request_new import apply_request, build_shortlist_rows


def test_apply_request_creates_request_and_upserts_suppliers(tmp_path):
    suppliers = JsonlStore(tmp_path / "s.jsonl", Supplier)
    requests_ = JsonlStore(tmp_path / "r.jsonl", Request)
    result = ResearchResult(
        shortlist=[
            Candidate(name="New Co", source="places", phone="+441626000001"),
            Candidate(name="Old Friend", source="book"),
        ],
        indicative={"low": 100, "high": 300, "sources": 2, "note": ""},
        stages={},
        caps=RunCaps(10, 8),
    )
    suppliers.upsert(Supplier(id="s-0001", name="Old Friend"))

    created = {}

    def fake_sheet(title, values):
        created["title"] = title
        return ("SID123", "https://sheet.example/SID123")

    req = apply_request(
        raw_need="tree down",
        triage_dict={"category": "trees-grounds"},
        constraints={"radius_miles": 15, "needed_by": None},
        result=result,
        suppliers=suppliers,
        requests=requests_,
        create_sheet_fn=fake_sheet,
        now=dt.datetime(2026, 6, 10, 15, 58),
    )
    assert req.id == "r-0001" and req.sheet_id == "SID123" and req.status == "open"
    assert "tree" in created["title"].lower() or "Procurement" in created["title"]
    names = {supplier.name for supplier in suppliers.all()}
    assert names == {"Old Friend", "New Co"}
    assert requests_.get("r-0001").shortlist[0].supplier_id


def test_excluded_rows_dropped_everywhere(tmp_path):
    suppliers = JsonlStore(tmp_path / "s.jsonl", Supplier)
    requests_ = JsonlStore(tmp_path / "r.jsonl", Request)
    result = ResearchResult(
        shortlist=[Candidate(name="Keep", source="places"), Candidate(name="Drop", source="web")],
        indicative=None,
        stages={},
        caps=RunCaps(1, 1),
    )
    req = apply_request(
        "need",
        {},
        {},
        result,
        suppliers,
        requests_,
        create_sheet_fn=lambda title, values: ("S", "u"),
        now=dt.datetime(2026, 6, 10),
        excluded_names={"Drop"},
    )
    assert len(req.shortlist) == 1
    assert {supplier.name for supplier in suppliers.all()} == {"Keep"}


def test_build_shortlist_rows_marks_call_vs_draft():
    rows = build_shortlist_rows(
        [
            Candidate(name="HasEmail", source="places", email="a@b.c"),
            Candidate(name="PhoneOnly", source="yell", phone="+447700900123"),
        ]
    )
    assert rows[0]["mode"] == "email" and rows[1]["mode"] == "call"
