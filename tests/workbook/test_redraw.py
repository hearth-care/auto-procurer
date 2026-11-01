import datetime as dt

from workbook.fakes import FakeStore, FakeWorkbookClient
from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.workbook.contract import ENERGY_JOB_COLUMNS, JOB_COLUMNS
from xsource.workbook.readback import read_job_edits
from xsource.workbook.redraw import migrate_open_requests, redraw_workbook

NOW = dt.datetime(2026, 11, 3, 10, 0, tzinfo=dt.UTC)


def _suppliers():
    return FakeStore(
        [
            Supplier(id="s-1", name="Acme Testing", phone="01632 960001"),
            Supplier(id="s-2", name="Example Sparks Ltd", phone="01632 960002"),
        ]
    )


def _job(**kw):
    base = dict(
        id="r-1",
        created_at="2026-11-01T09:00:00+00:00",
        raw_need="an EICR",
        title="EICR",
        job_tab="EICR Nov 2026",
        job_tab_gid=5,
        stage="Calling",
        next_step="Ring 2 firms on the call list",
        waiting_on="You: ring 2 firms",
        shortlist=[
            ShortlistEntry(supplier_id="s-1", rank=1),
            ShortlistEntry(supplier_id="s-2", rank=2),
        ],
    )
    base.update(kw)
    return Request(**base)


def _edited_tab(**cells):
    row = dict.fromkeys(JOB_COLUMNS, "")
    row.update({"Firm": "Example Sparks Ltd"})
    row.update({k.replace("_", " ").capitalize(): v for k, v in cells.items()})
    return [list(JOB_COLUMNS), [row[c] for c in JOB_COLUMNS]]


def _legacy():
    return Request(
        id="r-old",
        created_at="2026-10-01T09:00:00+00:00",
        raw_need="old thing",
        sheet_id="old-sheet",
        job_tab=None,
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],
    )


def test_redraw_reads_back_before_writing_and_skips_legacy():
    client = FakeWorkbookClient(tabs={"EICR Nov 2026": _edited_tab(latest_price="£1,250.50")})
    requests = FakeStore([_job(), _legacy()])
    report = redraw_workbook(
        workbook_id="wb",
        client=client,
        suppliers=_suppliers(),
        requests=requests,
        log=FakeStore(),
        now=NOW,
    )
    assert client.calls[0] == ("read_tab", "EICR Nov 2026")
    assert client.calls.index(("read_tab", "EICR Nov 2026")) < client.calls.index(
        ("write_tab", "EICR Nov 2026")
    )
    assert ("write_tab", "Board") in client.calls
    assert ("write_tab", "Black book") in client.calls
    assert ("write_tab", "Log") in client.calls
    assert not any(name == "Old request" or name.startswith("Old") for _, name in client.calls)
    assert report == {"jobs": 1, "warnings": []}
    saved = requests.get("r-1")
    assert saved.shortlist[1].latest_price_minor == 125050
    assert saved.stage == "Waiting for prices"
    assert client.formatted == []
    sparks_row = client.written["EICR Nov 2026"][2]
    assert sparks_row[JOB_COLUMNS.index("Latest price")] == "1250.50"


def test_redraw_logs_stage_change_against_the_request():
    client = FakeWorkbookClient(tabs={"EICR Nov 2026": _edited_tab(stage="Emailed")})
    log = FakeStore()
    redraw_workbook(
        workbook_id="wb",
        client=client,
        suppliers=_suppliers(),
        requests=FakeStore([_job()]),
        log=log,
        now=NOW,
    )
    [entry] = log.all()
    assert entry.request_id == "r-1"
    assert entry.text == "Stage: Calling → Waiting for prices"
    assert entry.at == NOW.isoformat()
    assert client.written["Log"][1][1:] == ["EICR Nov 2026", entry.text]


def test_redraw_with_no_changes_adds_no_log_lines():
    client = FakeWorkbookClient(tabs={"EICR Nov 2026": _edited_tab()})
    requests, log = FakeStore([_job()]), FakeStore()
    redraw_workbook(
        workbook_id="wb", client=client, suppliers=_suppliers(), requests=requests, log=log, now=NOW
    )
    assert log.all() == []
    assert requests.upserted == []


def test_redraw_saves_black_book_hand_edits():
    black_book = [
        ["Kind of job", "Firm", "Contact", "Notice to give"],
        ["EICR", "Acme Testing", "Sam", "28"],
    ]
    suppliers = _suppliers()
    redraw_workbook(
        workbook_id="wb",
        client=FakeWorkbookClient(tabs={"Black book": black_book}),
        suppliers=suppliers,
        requests=FakeStore(),
        log=FakeStore(),
        now=NOW,
    )
    saved = suppliers.get("s-1")
    assert (saved.contact_name, saved.notice_days) == ("Sam", 28)
    assert suppliers.upserted == [saved]


def test_redraw_returns_readback_warnings():
    client = FakeWorkbookClient(tabs={"EICR Nov 2026": _edited_tab(stage="Perhaps")})
    report = redraw_workbook(
        workbook_id="wb",
        client=client,
        suppliers=_suppliers(),
        requests=FakeStore([_job()]),
        log=FakeStore(),
        now=NOW,
    )
    assert report["warnings"] == [
        "EICR Nov 2026: 'Perhaps' is not a stage, ignored for Example Sparks Ltd"
    ]


def test_energy_job_reads_back_yearly_cost_and_quote_terms():
    row = dict.fromkeys(ENERGY_JOB_COLUMNS, "")
    row.update(
        {"Firm": "Acme Testing", "Term": "24", "Unit rate": "24.5", "Est. yearly cost": "£3,100"}
    )
    rows = [list(ENERGY_JOB_COLUMNS), [row[c] for c in ENERGY_JOB_COLUMNS]]
    req = _job(energy=True)
    read_job_edits(rows, req, {s.id: s for s in _suppliers().all()}, on=NOW.date())
    e = req.shortlist[0]
    assert e.latest_price_minor == 310000
    assert e.energy_quote == {"term": "24", "unit_rate": "24.5"}


class _Legacy:
    def __init__(self):
        self.reads = []

    def read_request_rows(self, sheet_id):
        self.reads.append(sheet_id)
        return [{"rank": 1, "status": "Quoted", "quote": "185", "chosen": "", "notes": ""}]


def test_migrate_moves_open_sheet_requests_into_new_tabs():
    legacy_req = _legacy()
    legacy_req.triage = {"category": "Boiler service"}
    requests = FakeStore([legacy_req, _job()])
    client, log, sheets = FakeWorkbookClient(), FakeStore(), _Legacy()
    moved = migrate_open_requests(
        workbook_id="wb",
        client=client,
        legacy_sheets=sheets,
        suppliers=_suppliers(),
        requests=requests,
        log=log,
        now=NOW,
    )
    assert moved == ["r-old -> Boiler service Oct 2026"]
    saved = requests.get("r-old")
    assert saved.job_tab == "Boiler service Oct 2026" and saved.job_tab_gid == 3
    assert saved.title == "Boiler service"
    assert saved.shortlist[0].latest_price_minor == 18500
    assert client.formatted == [(3, "job")]
    assert sheets.reads == ["old-sheet"]
    [entry] = log.all()
    assert (entry.request_id, entry.text) == ("r-old", "Moved from its old Sheet")


def test_migrate_dry_run_changes_nothing(monkeypatch):
    from typer.testing import CliRunner

    from xsource.cli import app
    from xsource.cli import workbook as cli_workbook

    requests, client = FakeStore([_legacy()]), FakeWorkbookClient()
    monkeypatch.setenv("XSOURCE_WORKBOOK_ID", "wb")
    monkeypatch.setattr(cli_workbook, "build_stores", lambda cfg: (_suppliers(), requests, None))
    monkeypatch.setattr(cli_workbook, "_workbook_client", lambda: client)
    monkeypatch.setattr(cli_workbook, "_legacy_sheets", lambda: _Legacy())
    result = CliRunner().invoke(app, ["workbook", "migrate"])
    assert result.exit_code == 0
    assert "r-old" in result.stdout
    assert client.calls == [] and client.formatted == []
    assert requests.upserted == [] and requests.get("r-old").job_tab is None
