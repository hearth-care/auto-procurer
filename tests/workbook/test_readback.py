import datetime as dt

from xsource.store.models import Request, ShortlistEntry, Supplier
from xsource.workbook.contract import JOB_COLUMNS
from xsource.workbook.layout import job_tab_rows
from xsource.workbook.readback import (
    job_key,
    parse_money_minor,
    read_black_book_edits,
    read_job_edits,
    snapshot_rows,
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


def _drawn(req, suppliers):
    return snapshot_rows(job_tab_rows(req, suppliers), job_key)


def _read(rows, req, suppliers):
    return read_job_edits(rows, req, suppliers, on=ON, drawn=_drawn(req, suppliers))


BB_DRAWN = {
    "eicr|acme testing": {"Phone": "'01632 960001", "Contract ends": "", "Notice to give": ""},
    "eicr|nobody ltd": {},
}


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
    assert _read(rows, req, _suppliers()) == []
    assert _entry(req, "Example Sparks Ltd").latest_price_minor == 125050
    assert _entry(req, "Example Sparks Ltd").stage == "Quoted"
    assert _entry(req, "Acme Testing").stage == "Declined"


def test_unknown_firm_row_is_a_warning_and_creates_nothing():
    rows = [list(JOB_COLUMNS), _row(firm="Someone New")]
    req = _job(firms=["Acme Testing"])
    assert _read(rows, req, _suppliers()) == [
        "EICR Nov 2026: no firm called 'Someone New' on this job"
    ]
    assert len(req.shortlist) == 1


def test_stage_typed_outside_the_list_is_ignored_with_a_warning():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", stage="Maybe later")]
    req = _job(firms=["Acme Testing"])
    assert _read(rows, req, _suppliers()) == [
        "EICR Nov 2026: 'Maybe later' is not a stage, ignored for Acme Testing"
    ]
    assert req.shortlist[0].stage == "To call"


def test_phone_edit_is_saved_to_the_supplier():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", phone="'01632 960009")]
    suppliers = _suppliers()
    _read(rows, _job(firms=["Acme Testing"]), suppliers)
    assert suppliers["s-1"].phone == "01632 960009"


def test_phone_typed_without_spaces_is_normalised():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", phone="01632960009")]
    suppliers = _suppliers()
    _read(rows, _job(firms=["Acme Testing"]), suppliers)
    assert suppliers["s-1"].phone == "01632 960009"


def test_empty_cells_do_not_clear_stored_values():
    req = _job(firms=["Acme Testing"])
    req.shortlist[0].contact_name = "Sam"
    req.shortlist[0].notes = "rings back"
    suppliers = _suppliers()
    suppliers["s-1"].email = "sam@example.test"
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing")]
    _read(rows, req, suppliers)
    assert req.shortlist[0].contact_name == "Sam"
    assert req.shortlist[0].notes == "rings back"
    assert suppliers["s-1"].email == "sam@example.test"
    assert suppliers["s-1"].phone == "01632 960001"


def test_price_edit_keeps_the_last_contact_channel_and_first_price():
    req = _job(firms=["Acme Testing"])
    req.shortlist[0].last_contact = {"date": "2026-11-01", "via": "phone"}
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£300")]
    _read(rows, req, _suppliers())
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
    _read(rows, req, _suppliers())
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
    assert read_black_book_edits(rows, [s], drawn=BB_DRAWN) == [
        "Black book: no firm called 'Nobody Ltd'"
    ]
    assert (s.contact_name, s.phone, s.email) == ("Sam", "01632 960077", "sam@example.test")
    assert (s.contract_ends, s.notice_days) == ("2026-12-01", 30)


def test_black_book_bad_date_is_a_warning():
    s = _suppliers()["s-1"]
    rows = [["Kind of job", "Firm", "Contract ends"], ["EICR", "Acme Testing", "soon"]]
    assert read_black_book_edits(rows, [s], drawn=BB_DRAWN) == [
        "Black book: 'soon' is not a date, ignored for Acme Testing"
    ]
    assert s.contract_ends is None


def test_a_tab_with_no_snapshot_yields_no_edits():
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£300")]
    req = _job(firms=["Acme Testing"])
    assert read_job_edits(rows, req, _suppliers(), on=ON, drawn=None) == []
    assert req.shortlist[0].latest_price_minor is None


def test_cell_equal_to_what_was_drawn_is_not_an_edit_even_if_the_store_moved_on():
    req = _job(firms=["Acme Testing"])
    e = req.shortlist[0]
    e.first_price_minor = e.latest_price_minor = 30000
    e.stage = "Quoted"
    suppliers = _suppliers()
    drawn = _drawn(req, suppliers)
    e.latest_price_minor, e.stage = 25000, "Declined"
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£300.00", stage="Quoted")]
    assert read_job_edits(rows, req, suppliers, on=ON, drawn=drawn) == []
    assert (e.latest_price_minor, e.stage) == (25000, "Declined")


def test_money_cells_compare_by_value():
    req = _job(firms=["Acme Testing"])
    e = req.shortlist[0]
    e.first_price_minor = e.latest_price_minor = 78000
    suppliers = _suppliers()
    drawn = _drawn(req, suppliers)
    e.latest_price_minor = 70000
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£780.00")]
    read_job_edits(rows, req, suppliers, on=ON, drawn=drawn)
    assert e.latest_price_minor == 70000


def test_price_edit_on_a_booked_row_keeps_it_booked():
    req = _job(firms=["Acme Testing"])
    e = req.shortlist[0]
    e.first_price_minor = e.latest_price_minor = 30000
    e.stage = "Booked"
    rows = [list(JOB_COLUMNS), _row(firm="Acme Testing", latest_price="£280", stage="Booked")]
    assert _read(rows, req, _suppliers()) == []
    assert (e.latest_price_minor, e.stage) == (28000, "Booked")


def test_a_uk_date_shown_for_the_drawn_iso_date_is_not_an_edit():
    s = _suppliers()["s-1"]
    s.contract_ends = "2026-03-04"
    rows = [["Kind of job", "Firm", "Contract ends"], ["EICR", "Acme Testing", "04/03/2026"]]
    drawn = {"eicr|acme testing": {"Contract ends": "2026-03-04"}}
    assert read_black_book_edits(rows, [s], drawn=drawn) == []
    assert s.contract_ends == "2026-03-04"
    rows[1][2] = "05/03/2026"
    read_black_book_edits(rows, [s], drawn=drawn)
    assert s.contract_ends == "2026-03-05"
