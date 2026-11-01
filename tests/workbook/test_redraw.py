import datetime as dt

from workbook.fakes import FakeStore, FakeWorkbookClient
from xsource.store.files import SyncedFile
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


def _edit(rows, firm="Example Sparks Ltd", **cells):
    out = [list(r) for r in rows]
    for row in out[1:]:
        if row[JOB_COLUMNS.index("Firm")] == firm:
            for header, value in cells.items():
                row[JOB_COLUMNS.index(header)] = value
    return out


def _redraw(client, suppliers, requests, log, drawn_file):
    return redraw_workbook(
        workbook_id="wb",
        client=client,
        suppliers=suppliers,
        requests=requests,
        log=log,
        drawn_file=drawn_file,
        now=NOW,
    )


def _drawn_file(tmp_path):
    return SyncedFile(tmp_path / "workbook-drawn.json", blob=None)


def _legacy():
    return Request(
        id="r-old",
        created_at="2026-10-01T09:00:00+00:00",
        raw_need="old thing",
        sheet_id="old-sheet",
        job_tab=None,
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],
    )


def test_redraw_reads_back_before_writing_and_skips_legacy(tmp_path):
    client, df = FakeWorkbookClient(), _drawn_file(tmp_path)
    requests = FakeStore([_job(), _legacy()])
    suppliers, log = _suppliers(), FakeStore()
    _redraw(client, suppliers, requests, log, df)
    client.calls.clear()
    client.tabs["EICR Nov 2026"] = _edit(
        client.written["EICR Nov 2026"], **{"Latest price": "£1,250.50"}
    )
    report = _redraw(client, suppliers, requests, log, df)
    assert client.calls[0] == ("read_tab", "EICR Nov 2026")
    assert client.calls.index(("read_tab", "EICR Nov 2026")) < client.calls.index(
        ("write_tab", "EICR Nov 2026")
    )
    for tab in ("Board", "Black book", "Log"):
        assert ("write_tab", tab) in client.calls
    assert not any(name.startswith("Old") for _, name in client.calls)
    assert report == {"jobs": 1, "warnings": []}
    saved = requests.get("r-1")
    assert saved.shortlist[1].latest_price_minor == 125050
    assert saved.stage == "Waiting for prices"
    assert client.formatted == []
    assert client.written["EICR Nov 2026"][2][JOB_COLUMNS.index("Latest price")] == "1250.50"


def test_first_redraw_has_no_snapshot_so_reads_nothing_back(tmp_path):
    client = FakeWorkbookClient(
        tabs={"EICR Nov 2026": _edit([list(JOB_COLUMNS), [""] * 15], firm="")}
    )
    client.tabs["EICR Nov 2026"][1][1] = "Example Sparks Ltd"
    client.tabs["EICR Nov 2026"][1][JOB_COLUMNS.index("Latest price")] = "£5"
    requests = FakeStore([_job()])
    _redraw(client, _suppliers(), requests, FakeStore(), _drawn_file(tmp_path))
    assert requests.get("r-1").shortlist[1].latest_price_minor is None


def test_redraw_logs_stage_change_against_the_request(tmp_path):
    client, df, log = FakeWorkbookClient(), _drawn_file(tmp_path), FakeStore()
    suppliers, requests = _suppliers(), FakeStore([_job()])
    _redraw(client, suppliers, requests, log, df)
    client.tabs["EICR Nov 2026"] = _edit(client.written["EICR Nov 2026"], Stage="Emailed")
    _redraw(client, suppliers, requests, log, df)
    [entry] = log.all()
    assert entry.request_id == "r-1"
    assert entry.text == "Stage: Calling → Waiting for prices"
    assert entry.at == NOW.isoformat()
    assert client.written["Log"][1][1:] == ["EICR Nov 2026", entry.text]


def test_redraw_with_no_changes_adds_no_log_lines_and_saves_nothing(tmp_path):
    client, df, log = FakeWorkbookClient(), _drawn_file(tmp_path), FakeStore()
    suppliers, requests = _suppliers(), FakeStore([_job()])
    _redraw(client, suppliers, requests, log, df)
    log.upserted.clear()
    requests.upserted.clear()
    suppliers.upserted.clear()
    _redraw(client, suppliers, requests, log, df)
    assert log.upserted == [] and requests.upserted == [] and suppliers.upserted == []


def test_no_edit_redraw_with_contact_names_and_an_energy_job_leaves_the_store_alone(tmp_path):
    suppliers = _suppliers()
    suppliers.get("s-1").contact_name = "Sam"
    suppliers.get("s-2").contact_name = "Pat"
    plain = _job(shortlist=[ShortlistEntry(supplier_id="s-1", rank=1, contact_name="Sam B")])
    energy = _job(
        id="r-2",
        job_tab="Energy Nov 2026",
        energy=True,
        triage={"category": "Energy"},
        status="closed",
        chosen_supplier_id="s-2",
        shortlist=[
            ShortlistEntry(
                supplier_id="s-2",
                rank=1,
                stage="Booked",
                latest_price_minor=310000,
                energy_quote={"term": "24", "unit_rate": "24.5", "standing_charge": "61.2"},
            )
        ],
    )
    requests, log, client = FakeStore([plain, energy]), FakeStore(), FakeWorkbookClient()
    df = _drawn_file(tmp_path)
    _redraw(client, suppliers, requests, log, df)
    log.upserted.clear()
    requests.upserted.clear()
    suppliers.upserted.clear()
    # Sheets hands numbers back reformatted by the cell format.
    rate = ENERGY_JOB_COLUMNS.index("Unit rate")
    client.tabs["Energy Nov 2026"] = [list(r) for r in client.written["Energy Nov 2026"]]
    client.tabs["Energy Nov 2026"][1][rate] = "24.50"
    report = _redraw(client, suppliers, requests, log, df)
    assert report["warnings"] == []
    assert log.upserted == [] and requests.upserted == [] and suppliers.upserted == []
    assert energy.shortlist[0].energy_quote["unit_rate"] == "24.5"
    assert plain.shortlist[0].contact_name == "Sam B"


def test_job_tab_phone_edit_survives_the_black_book_row_for_the_same_firm(tmp_path):
    suppliers = _suppliers()
    suppliers.get("s-2").preferred = True
    suppliers.get("s-2").categories = ["EICR"]
    client, df = FakeWorkbookClient(), _drawn_file(tmp_path)
    requests, log = FakeStore([_job()]), FakeStore()
    _redraw(client, suppliers, requests, log, df)
    assert client.written["Black book"][1][1] == "Example Sparks Ltd"
    client.tabs["EICR Nov 2026"] = _edit(client.written["EICR Nov 2026"], Phone="'01632 960099")
    _redraw(client, suppliers, requests, log, df)
    assert suppliers.get("s-2").phone == "01632 960099"
    assert client.written["Black book"][1][3] == "'01632 960099"


def test_store_price_changed_after_a_draw_is_not_reverted_by_the_next_redraw(tmp_path):
    client, df, log = FakeWorkbookClient(), _drawn_file(tmp_path), FakeStore()
    suppliers, requests = _suppliers(), FakeStore([_job()])
    _redraw(client, suppliers, requests, log, df)
    watcher_entry = requests.get("r-1").shortlist[1]
    watcher_entry.first_price_minor = watcher_entry.latest_price_minor = 78000
    watcher_entry.stage = "Quoted"
    _redraw(client, suppliers, requests, log, df)
    assert (watcher_entry.latest_price_minor, watcher_entry.stage) == (78000, "Quoted")
    assert client.written["EICR Nov 2026"][2][JOB_COLUMNS.index("Latest price")] == "780"


def test_a_job_tab_deleted_by_hand_is_reported_and_other_jobs_still_redraw(tmp_path):
    gone = _job(id="r-2", job_tab="Gone Nov 2026", job_tab_gid=9)
    client = FakeWorkbookClient(missing={"Gone Nov 2026"})
    report = _redraw(
        client, _suppliers(), FakeStore([_job(), gone]), FakeStore(), _drawn_file(tmp_path)
    )
    assert report == {"jobs": 1, "warnings": ["Gone Nov 2026: tab missing, not redrawn"]}
    assert ("write_tab", "EICR Nov 2026") in client.calls
    assert ("write_tab", "Gone Nov 2026") not in client.calls
    assert not any(c == "ensure_tab" for c, _ in client.calls)


def test_redraw_saves_black_book_hand_edits(tmp_path):
    suppliers = _suppliers()
    suppliers.get("s-1").preferred = True
    suppliers.get("s-1").categories = ["EICR"]
    client, df = FakeWorkbookClient(), _drawn_file(tmp_path)
    _redraw(client, suppliers, FakeStore(), FakeStore(), df)
    book = [list(r) for r in client.written["Black book"]]
    book[1][2], book[1][8] = "Sam", "28"
    client.tabs["Black book"] = book
    _redraw(client, suppliers, FakeStore(), FakeStore(), df)
    saved = suppliers.get("s-1")
    assert (saved.contact_name, saved.notice_days) == ("Sam", 28)


def test_redraw_returns_readback_warnings(tmp_path):
    client, df = FakeWorkbookClient(), _drawn_file(tmp_path)
    suppliers, requests = _suppliers(), FakeStore([_job()])
    _redraw(client, suppliers, requests, FakeStore(), df)
    client.tabs["EICR Nov 2026"] = _edit(client.written["EICR Nov 2026"], Stage="Perhaps")
    report = _redraw(client, suppliers, requests, FakeStore(), df)
    assert report["warnings"] == [
        "EICR Nov 2026: 'Perhaps' is not a stage, ignored for Example Sparks Ltd"
    ]


def test_energy_job_reads_back_yearly_cost_and_quote_terms():
    req = _job(energy=True)
    suppliers = {s.id: s for s in _suppliers().all()}
    from xsource.workbook.layout import job_tab_rows
    from xsource.workbook.readback import job_key, snapshot_rows

    drawn = snapshot_rows(job_tab_rows(req, suppliers), job_key)
    row = dict.fromkeys(ENERGY_JOB_COLUMNS, "")
    row.update(
        {"Firm": "Acme Testing", "Term": "24", "Unit rate": "24.5", "Est. yearly cost": "£3,100"}
    )
    rows = [list(ENERGY_JOB_COLUMNS), [row[c] for c in ENERGY_JOB_COLUMNS]]
    read_job_edits(rows, req, suppliers, on=NOW.date(), drawn=drawn)
    e = req.shortlist[0]
    assert e.latest_price_minor == 310000
    assert e.energy_quote == {"term": "24", "unit_rate": "24.5"}


class _Legacy:
    def __init__(self):
        self.reads = []

    def read_request_rows(self, sheet_id):
        self.reads.append(sheet_id)
        return [{"rank": 1, "status": "Quoted", "quote": "185", "chosen": "", "notes": ""}]


def test_migrate_moves_open_sheet_requests_into_new_tabs(tmp_path):
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
        drawn_file=_drawn_file(tmp_path),
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
