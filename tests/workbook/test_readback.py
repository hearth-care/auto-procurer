import datetime as dt

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.workbook.contract import JOB_COLUMNS
from xsource.workbook.readback import (
    parse_money_minor,
    read_black_book_edits,
    read_job_edits,
)

ON = dt.date(2026, 11, 3)


def _suppliers():
    return {
        "s-1": Supplier(id="s-1", name="Acme Testing", phone="01632 960001"),
        "s-2": Supplier(id="s-2", name="Example Sparks Ltd", phone="01632 960002"),
    }


def _job(firms=("Acme Testing", "Example Sparks Ltd")):
    ids = {"Acme Testing": "s-1", "Example Sparks Ltd": "s-2"}
    return Request(
        id="r-1",
        created_at="2026-11-01T09:00:00+00:00",
        raw_need="an EICR",
        job_tab="EICR Nov 2026",
        shortlist=[ShortlistEntry(supplier_id=ids[f], rank=i) for i, f in enumerate(firms, 1)],
    )


def _row(**cells):
    row = dict.fromkeys(JOB_COLUMNS, "")
    row.update({k.replace("_", " ").capitalize(): v for k, v in cells.items()})
    return [row[c] for c in JOB_COLUMNS]


def _entry(req, firm):
    sid = {"Acme Testing": "s-1", "Example Sparks Ltd": "s-2"}[firm]
    return next(e for e in req.shortlist if e.supplier_id == sid)


def test_money_parsing():
    assert parse_money_minor("£1,250.50") == 125050
    assert parse_money_minor("185") == 18500
    assert parse_money_minor("£99.5") == 9950
    assert parse_money_minor("") is None
    assert parse_money_minor("tbc") is None


def test_edits_match_by_firm_even_after_rows_are_sorted():
    rows = [
        list(JOB_COLUMNS),
        _row(firm="Example Sparks Ltd", latest_price="£1,250.50"),
        _row(firm="Acme Testing", stage="Declined"),
    ]
    req = _job()
    assert read_job_edits(rows, req, _suppliers(), on=ON) == []
    assert _entry(req, "Example Sparks Ltd").latest_price_minor == 125050
    assert _entry(req, "Example Sparks Ltd").stage == "Quoted"
    assert _entry(req, "Acme Testing").stage == "Declined"


def test_unknown_firm_row_is_a_warning_and_creates_nothing():
    rows = [list(JOB_COLUMNS), _row(firm="Someone New")]
    req = _job(firms=["Acme Testing"])
    assert read_job_edits(rows, req, _suppliers(), on=ON) == [
        "EICR Nov 2026: no firm called 'Someone New' on this job"
    ]
    assert len(req.shortlist) == 1


def test_stage_typed_outside_the_list_is_ignored_with_a_warning():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", stage="Maybe later")]
    req = _job(firms=["Acme Testing"])
    assert read_job_edits(rows, req, _suppliers(), on=ON) == [
        "EICR Nov 2026: 'Maybe later' is not a stage, ignored for Acme Testing"
    ]
    assert req.shortlist[0].stage == "To call"


def test_phone_edit_is_saved_to_the_supplier():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", phone="'01632 960009")]
    suppliers = _suppliers()
    read_job_edits(rows, _job(firms=["Acme Testing"]), suppliers, on=ON)
    assert suppliers["s-1"].phone == "01632 960009"


def test_phone_typed_without_spaces_is_normalised():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", phone="01632960009")]
    suppliers = _suppliers()
    read_job_edits(rows, _job(firms=["Acme Testing"]), suppliers, on=ON)
    assert suppliers["s-1"].phone == "01632 960009"


def test_empty_cells_do_not_clear_stored_values():
    req = _job(firms=["Acme Testing"])
    req.shortlist[0].contact_name = "Sam"
    req.shortlist[0].notes = "rings back"
    suppliers = _suppliers()
    suppliers["s-1"].email = "sam@example.test"
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing")]
    read_job_edits(rows, req, suppliers, on=ON)
    assert req.shortlist[0].contact_name == "Sam"
    assert req.shortlist[0].notes == "rings back"
    assert suppliers["s-1"].email == "sam@example.test"
    assert suppliers["s-1"].phone == "01632 960001"


def test_price_edit_keeps_the_last_contact_channel_and_first_price():
    req = _job(firms=["Acme Testing"])
    req.shortlist[0].last_contact = {"date": "2026-11-01", "via": "phone"}
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£300")]
    read_job_edits(rows, req, _suppliers(), on=ON)
    e = req.shortlist[0]
    assert e.last_contact == {"date": "2026-11-03", "via": "phone"}
    assert e.first_price_minor == 30000 and e.latest_price_minor == 30000


def test_unchanged_price_does_not_touch_last_contact():
    req = _job(firms=["Acme Testing"])
    e = req.shortlist[0]
    e.first_price_minor = e.latest_price_minor = 30000
    e.stage = "Quoted"
    e.last_contact = {"date": "2026-11-01", "via": "email"}
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£300.00", stage="Quoted")]
    read_job_edits(rows, req, _suppliers(), on=ON)
    assert e.last_contact == {"date": "2026-11-01", "via": "email"}


def test_black_book_edits_update_the_supplier_by_firm():
    s = _suppliers()["s-1"]
    header = [
        "Kind of job", "Firm", "Contact", "Phone", "Email", "Last used", "Last price",
        "Contract ends", "Notice to give",
    ]  # fmt: skip
    rows = [
        header,
        [
            "EICR",
            "Acme Testing",
            "Sam",
            "'01632 960077",
            "sam@example.test",
            "",
            "",
            "01/12/2026",
            "30",
        ],
        ["EICR", "Nobody Ltd", "", "", "", "", "", "", ""],
    ]
    assert read_black_book_edits(rows, [s]) == ["Black book: no firm called 'Nobody Ltd'"]
    assert (s.contact_name, s.phone, s.email) == ("Sam", "01632 960077", "sam@example.test")
    assert (s.contract_ends, s.notice_days) == ("2026-12-01", 30)


def test_black_book_bad_date_is_a_warning():
    s = _suppliers()["s-1"]
    rows = [["Kind of job", "Firm", "Contract ends"], ["EICR", "Acme Testing", "soon"]]
    assert read_black_book_edits(rows, [s]) == [
        "Black book: 'soon' is not a date, ignored for Acme Testing"
    ]
    assert s.contract_ends is None
