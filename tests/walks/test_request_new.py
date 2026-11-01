import datetime as dt
from dataclasses import replace

from workbook.fakes import FakeWorkbookClient

from xsource.research.candidates import Candidate
from xsource.research.pipeline import ResearchResult, RunCaps
from xsource.store.files import SyncedFile
from xsource.store.jsonl import JsonlStore
from xsource.store.models import Request, Supplier
from xsource.walks.request_new import apply_request, build_shortlist_rows, shortlist_preview_rows


def _result(*cands):
    return ResearchResult(
        shortlist=list(cands),
        indicative={"low": 100, "high": 300, "sources": 2, "note": ""},
        stages={},
        caps=RunCaps(10, 8),
    )


class _Log:
    def __init__(self):
        self.entries = []

    def next_id(self, prefix):
        return f"{prefix}-{len(self.entries) + 1:04d}"

    def upsert(self, entry):
        self.entries.append(entry)


def test_apply_request_creates_request_and_upserts_suppliers(tmp_path):
    suppliers = JsonlStore(tmp_path / "s.jsonl", Supplier)
    requests_ = JsonlStore(tmp_path / "r.jsonl", Request)
    suppliers.upsert(Supplier(id="s-0001", name="Old Friend"))
    log = _Log()
    tabs = []

    def add_tab(request):
        tabs.append(request.title)
        return ("EICR Jun 2026", 7)

    req = apply_request(
        raw_need="tree down",
        triage_dict={"category": "trees-grounds", "short_label": "Tree"},
        constraints={"radius_miles": 15, "needed_by": None},
        result=_result(
            Candidate(name="New Co", source="places", phone="+441626000001", extra={"miles": 3.2}),
            Candidate(name="Old Friend", source="book"),
        ),
        suppliers=suppliers,
        requests=requests_,
        add_job_tab_fn=add_tab,
        log=log,
        now=dt.datetime(2026, 6, 10, 15, 58),
    )
    assert tabs == ["Tree"]
    assert (req.id, req.status, req.stage) == ("r-0001", "open", "Calling")
    assert (req.job_tab, req.job_tab_gid, req.title, req.energy) == (
        "EICR Jun 2026",
        7,
        "Tree",
        False,
    )
    assert requests_.get("r-0001").job_tab == "EICR Jun 2026"
    assert {s.name for s in suppliers.all()} == {"Old Friend", "New Co"}
    assert [e.miles for e in req.shortlist] == [3.2, None]
    assert [e.request_id for e in log.entries] == ["r-0001"]


def test_title_falls_back_to_category_then_raw_need(tmp_path):
    def run(triage, need):
        return apply_request(
            need,
            triage,
            {},
            _result(Candidate(name="A", source="places")),
            JsonlStore(tmp_path / "s.jsonl", Supplier),
            JsonlStore(tmp_path / "r.jsonl", Request),
            add_job_tab_fn=lambda r: ("T", 1),
            log=_Log(),
            now=dt.datetime(2026, 6, 10),
        )

    assert run({"category": "energy"}, "x").title == "energy"
    assert run({}, "  fix   the   boiler " + "z" * 60).title == ("fix the boiler " + "z" * 60)[:40]


def test_energy_category_marks_request_energy(tmp_path):
    req = apply_request(
        "gas contract",
        {"category": "energy"},
        {},
        _result(Candidate(name="A", source="places")),
        JsonlStore(tmp_path / "s.jsonl", Supplier),
        JsonlStore(tmp_path / "r.jsonl", Request),
        add_job_tab_fn=lambda r: ("T", 1),
        log=_Log(),
        now=dt.datetime(2026, 6, 10),
    )
    assert req.energy is True


def test_excluded_rows_dropped_everywhere(tmp_path):
    suppliers = JsonlStore(tmp_path / "s.jsonl", Supplier)
    requests_ = JsonlStore(tmp_path / "r.jsonl", Request)
    req = apply_request(
        "need",
        {},
        {},
        _result(Candidate(name="Keep", source="places"), Candidate(name="Drop", source="web")),
        suppliers,
        requests_,
        add_job_tab_fn=lambda r: ("T", 1),
        log=_Log(),
        now=dt.datetime(2026, 6, 10),
        excluded_names={"Drop"},
    )
    assert len(req.shortlist) == 1
    assert {supplier.name for supplier in suppliers.all()} == {"Keep"}


def test_shortlist_preview_rows_show_miles_phone_and_source():
    rows = shortlist_preview_rows(
        [
            Candidate(name="Near Co", source="places", phone="+447700900123", extra={"miles": 3.2}),
            Candidate(name="Book Co", source="book", phone="01632960123"),
        ]
    )
    assert rows[0].split("  ") == [" 1", "Near Co", "3.2 mi", "07700 900123", "Google"]
    assert rows[1].split("  ") == [" 2", "Book Co", "—", "01632 960123", "black book"]


def _wired_review(monkeypatch, tmp_path, *, confirm):
    from xsource.cli import cockpit
    from xsource.config import Config

    real = Config.from_env
    real = real.__func__.__get__(Config)

    events = []
    suppliers = JsonlStore(tmp_path / "s.jsonl", Supplier)
    requests_ = JsonlStore(tmp_path / "r.jsonl", Request)
    fake = FakeWorkbookClient()
    monkeypatch.setenv("XSOURCE_SHEETS_TOKEN_PATH", "/nonexistent")
    monkeypatch.setattr(
        Config, "from_env", classmethod(lambda cls: replace(real(), workbook_id="WB"))
    )
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: (suppliers, requests_, object()))
    monkeypatch.setattr(cockpit, "build_log_store", lambda cfg: _Log())
    drawn_file = SyncedFile(tmp_path / "workbook-drawn.json", blob=None)
    monkeypatch.setattr(cockpit, "build_drawn_state_file", lambda cfg: drawn_file)
    monkeypatch.setattr(
        cockpit.Credentials, "from_authorized_user_file", staticmethod(lambda path: object())
    )
    monkeypatch.setattr("xsource.workbook.client.WorkbookClient", lambda creds: fake)
    monkeypatch.setattr(
        "xsource.workbook.redraw.redraw_workbook", lambda **kw: events.append("redraw")
    )

    def recording_confirm(ctx, *, prompt, equivalent_cli):
        events.append("confirm")
        return confirm

    monkeypatch.setattr(cockpit, "confirm_apply", recording_confirm)
    console = type("C", (), {"print": lambda self, text, *a, **k: events.append(f"print {text}")})()
    ctx = type("Ctx", (), {"console": console})()
    bag = {
        "raw_need": "tree down",
        "triage": {"category": "trees-grounds", "short_label": "Tree"},
        "constraints": {},
        "result": _result(Candidate(name="Near Co", source="places", extra={"miles": 3.2})),
    }
    return cockpit, ctx, bag, fake, suppliers, requests_, events, drawn_file


def test_review_prints_shortlist_before_asking_to_confirm(monkeypatch, tmp_path):
    cockpit, ctx, bag, fake, _s, requests_, events, _ = _wired_review(
        monkeypatch, tmp_path, confirm=True
    )
    result = cockpit._review_apply_step(ctx, bag)
    assert result.ok
    firm_line = next(i for i, e in enumerate(events) if "Near Co" in e and "3.2 mi" in e)
    assert firm_line < events.index("confirm") < events.index("redraw")
    [request] = requests_.all()
    assert request.job_tab and request.stage == "Calling"
    assert fake.formatted == [(request.job_tab_gid, "job")]


def test_declining_creates_no_tab_and_no_records(monkeypatch, tmp_path):
    cockpit, ctx, bag, fake, suppliers, requests_, events, _ = _wired_review(
        monkeypatch, tmp_path, confirm=False
    )
    result = cockpit._review_apply_step(ctx, bag)
    assert not result.ok
    assert any("Near Co" in e for e in events) and events[-1] == "confirm"
    assert fake.formatted == [] and not any(c[0] == "ensure_tab" for c in fake.calls)
    assert suppliers.all() == [] and requests_.all() == []


def test_request_new_needs_a_workbook_configured(monkeypatch):
    from xsource.cli import cockpit
    from xsource.config import Config

    real = Config.from_env
    real = real.__func__.__get__(Config)

    monkeypatch.setattr(
        Config, "from_env", classmethod(lambda cls: replace(real(), workbook_id=None))
    )
    monkeypatch.setattr(
        cockpit,
        "_status",
        lambda: {
            "cfg": replace(real(), workbook_id=None),
            "suppliers": [],
            "requests": [],
            "invoices": [],
            "budget": type(
                "B", (), {"allow_new_run": lambda self: True, "level": lambda self: "ok"}
            )(),
        },
    )
    monkeypatch.setattr(cockpit, "_store_online", lambda *a: True)
    row = next(p for p in cockpit._preconditions(object()) if p.label == "Workbook")
    assert row.ok is False and "xsource workbook init" in row.detail


def test_build_shortlist_rows_marks_call_vs_draft():
    rows = build_shortlist_rows(
        [
            Candidate(name="HasEmail", source="places", email="a@b.c"),
            Candidate(name="PhoneOnly", source="yell", phone="+447700900123"),
        ]
    )
    assert rows[0]["mode"] == "email" and rows[1]["mode"] == "call"


def test_cockpit_steps_call_triage_and_research_pipeline(monkeypatch):
    from xsource.cli import cockpit
    from xsource.research.triage import Triage
    from xsource.store.models import Supplier

    triage = Triage(
        category="trees-grounds",
        search_terms=["tree surgeon"],
        also_try=[],
        email_vars={"job_summary": "tree down", "location_town": "Newton Abbot"},
    )
    calls = {}

    def fake_run_triage(raw_need, constraints, gateway):
        calls["triage"] = (raw_need, constraints)
        return triage

    class FakeSuppliers:
        def all(self):
            return [
                Supplier(
                    id="s-1",
                    name="Old Friend",
                    categories=["trees-grounds"],
                    phone="+441626000001",
                )
            ]

    def fake_run_research(**kwargs):
        calls["research"] = kwargs
        return ResearchResult(
            shortlist=[Candidate(name="Old Friend", source="book")],
            indicative=None,
            stages={},
            caps=kwargs["caps"],
        )

    monkeypatch.setattr(cockpit, "run_triage", fake_run_triage)
    monkeypatch.setattr(cockpit, "_AnthropicStructuredGateway", lambda chain=None: object())
    monkeypatch.setattr(cockpit, "build_stores", lambda cfg: (FakeSuppliers(), object(), object()))
    monkeypatch.setattr(
        cockpit,
        "build_research_fns",
        lambda cfg: {
            "places_fn": lambda term: [],
            "directory_fn": lambda term, site: [],
            "price_fn": lambda term: None,
            "ch_fn": lambda name: None,
            "contact_fn": lambda name, website: None,
        },
    )
    monkeypatch.setattr(cockpit, "run_research", fake_run_research)

    bag = {"raw_need": "tree down", "constraints": {"radius_miles": 15}}
    triage_result = cockpit._triage_step(object(), bag)
    bag.update(triage_result.data)
    research_result = cockpit._research_step(object(), bag)

    assert calls["triage"] == ("tree down", {"radius_miles": 15})
    assert calls["research"]["triage"] == triage
    assert [c.name for c in calls["research"]["book_matches"]] == ["Old Friend"]
    assert research_result.data["result"].shortlist[0].source == "book"


def test_a_new_tab_does_not_inherit_a_stale_snapshot_under_its_name(monkeypatch, tmp_path):
    import json

    cockpit, ctx, bag, _fake, _s, _r, _events, drawn_file = _wired_review(
        monkeypatch, tmp_path, confirm=True
    )
    drawn_file.path.write_text(json.dumps({"Tree Nov 2026": {"near co": {"Notes": "old"}}}))
    monkeypatch.setattr("xsource.workbook.redraw.add_job_tab", lambda **kw: ("Tree Nov 2026", 9))
    assert cockpit._review_apply_step(ctx, bag).ok
    assert "Tree Nov 2026" not in json.loads(drawn_file.path.read_text())
