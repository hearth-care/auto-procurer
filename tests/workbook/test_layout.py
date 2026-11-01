import datetime as dt

import pytest

from xsource.store.models import LogEntry, Request, ShortlistEntry, Supplier
from xsource.workbook import contract
from xsource.workbook.layout import (
    black_book_rows,
    board_rows,
    job_tab_name,
    job_tab_rows,
    log_rows,
    phone_cell,
    quote_tab,
)


def _job(tab, energy=False, created="2026-11-01T09:00:00+00:00", **kw):
    return Request(
        id=f"r-{tab}",
        created_at=created,
        raw_need="need",
        title=tab,
        job_tab=tab,
        job_tab_gid=42,
        energy=energy,
        **kw,
    )


def _supplier(**kw):
    base = {"id": "s-1", "name": "Acme Electrical", "phone": "+447700900001"}
    return Supplier(**{**base, **kw})


def _suppliers():
    return {"s-1": _supplier(email="hi@acme.example", contact_name="Pat")}


def _job_with_quote(first, latest, on, via):
    r = _job("EICR Nov 2026")
    r.shortlist = [
        ShortlistEntry(
            supplier_id="s-1",
            rank=1,
            stage="Quoted",
            first_price_minor=first,
            latest_price_minor=latest,
            last_contact={"date": on, "via": via},
        )
    ]
    return r


def _closed_job(**kw):
    r = _job(
        "EICR Nov 2026",
        status="closed",
        chosen_supplier_id="s-1",
        triage={"category": "Electrical"},
        **kw,
    )
    r.shortlist = [ShortlistEntry(supplier_id="s-1", rank=1, latest_price_minor=125050)]
    return r


def test_board_formulas_match_contract_with_row_numbers():
    row = board_rows([_job("EICR Nov 2026")], start_row=2)[0]
    assert row[3] == (
        "=COUNTIF('EICR Nov 2026'!I:I,\"Keen\")+COUNTIF('EICR Nov 2026'!I:I,\"Emailed\")"
        "+COUNTIF('EICR Nov 2026'!I:I,\"Quoted\")+COUNTIF('EICR Nov 2026'!I:I,\"Booked\")"
    )
    assert row[4] == "=COUNT('EICR Nov 2026'!K2:K)"
    assert row[5] == "=IF(E2=0,\"\",MIN('EICR Nov 2026'!K:K))"
    assert row[6].startswith("=IF(E2=0,\"\",INDEX('EICR Nov 2026'!B:B, MATCH(")
    assert row[1] == '=HYPERLINK("#gid=42","EICR Nov 2026")'


def test_board_lists_only_open_tabbed_jobs_newest_first():
    old = _job("Old Oct 2026", created="2026-10-01T09:00:00+00:00")
    new = _job("New Nov 2026")
    closed = _job("Shut Nov 2026", status="closed")
    untabbed = Request(id="r-x", created_at="2026-11-02T09:00:00+00:00", raw_need="n")
    rows = board_rows([old, closed, untabbed, new])
    assert [r[0] for r in rows] == ["'New Nov 2026", "'Old Oct 2026"]
    assert "E3" in rows[1][5]


def test_energy_job_board_reads_yearly_cost_column():
    row = board_rows([_job("Electricity Nov 2026", energy=True)])[0]
    assert "'Electricity Nov 2026'!M:M" in row[5]
    assert "'Electricity Nov 2026'!M2:M" in row[4]


def test_apostrophe_in_tab_name_is_doubled_in_formulas():
    row = board_rows([_job("O'Neill check Nov 2026")])[0]
    assert "'O''Neill check Nov 2026'!I:I" in row[3]
    assert quote_tab("O'Neill Nov 2026") == "'O''Neill Nov 2026'"


def test_tab_name_strips_forbidden_characters_and_numbers_clashes():
    d = dt.date(2026, 11, 1)
    assert job_tab_name("Gas/Heating: annual", d, set()) == "GasHeating annual Nov 2026"
    assert job_tab_name("EICR", d, {"EICR Nov 2026"}) == "EICR Nov 2026 (2)"
    assert job_tab_name("EICR", d, {"EICR Nov 2026", "EICR Nov 2026 (2)"}) == "EICR Nov 2026 (3)"


def test_tab_name_is_capped_at_ninety_characters_even_when_numbered():
    d = dt.date(2026, 11, 1)
    first = job_tab_name("x" * 200, d, set())
    second = job_tab_name("x" * 200, d, {first})
    assert len(first) == 90 and first.endswith(" Nov 2026")
    assert len(second) == 90 and second.endswith(" Nov 2026 (2)")


@pytest.mark.parametrize(
    "raw, cell",
    [
        ("+447700900001", "'07700 900001"),
        ("01632 960001", "'01632 960001"),
        ("07700900001", "'07700 900001"),
        (None, ""),
    ],
)
def test_phone_cells_keep_the_leading_zero(raw, cell):
    assert phone_cell(raw) == cell


def test_job_tab_row_shows_prices_in_pounds_and_last_contact():
    rows = job_tab_rows(
        _job_with_quote(first=78000, latest=72000, on="2026-11-05", via="email"), _suppliers()
    )
    assert rows[0] == list(contract.JOB_COLUMNS)
    assert rows[1][9:12] == ["780", "720", "'5 Nov · email"]
    assert rows[1][1:5] == ["Acme Electrical", "Pat", "'07700 900001", "hi@acme.example"]
    assert len(rows[1]) == len(contract.JOB_COLUMNS)


def test_job_tab_row_pence_thread_link_and_exclusions():
    r = _job_with_quote(first=125050, latest=125050, on="2026-11-05", via="email")
    r.shortlist[0].outreach = {"thread_id": "abc123"}
    r.shortlist[0].miles = 3.5
    r.shortlist.append(ShortlistEntry(supplier_id="s-2", rank=2, excluded=True))
    rows = job_tab_rows(r, _suppliers())
    assert len(rows) == 2
    assert rows[1][7] == "3.5" and rows[1][9] == "1250.50"
    assert rows[1][12] == ""
    assert rows[1][13] == '=HYPERLINK("https://mail.google.com/mail/u/0/#all/abc123","thread")'


def test_energy_job_tab_row_uses_energy_columns():
    r = _job("Electricity Nov 2026", energy=True)
    r.shortlist = [
        ShortlistEntry(
            supplier_id="s-1",
            rank=1,
            energy_quote={"term": "24 months", "unit_rate": "28.5p", "standing_charge": "45p"},
            latest_price_minor=410000,
            last_contact={"date": "2026-11-05", "via": "call"},
            notes="n",
        )
    ]
    rows = job_tab_rows(r, _suppliers())
    assert rows[0] == list(contract.ENERGY_JOB_COLUMNS)
    assert rows[1][9:14] == ["'24 months", "28.5p", "45p", "4100", "'5 Nov · call"]
    assert rows[1][16] == "n" and len(rows[1]) == len(contract.ENERGY_JOB_COLUMNS)


def test_black_book_tell_them_by_formula_per_row():
    rows = black_book_rows([_supplier(contract_ends="2027-03-31", notice_days=90)], [_closed_job()])
    assert rows[0] == list(contract.BLACK_BOOK_COLUMNS)
    assert rows[1][9] == '=IF(H2="","",H2-I2)'
    assert rows[1][7:9] == ["2027-03-31", "90"]
    assert rows[1][6] == "1250.50"
    assert rows[1][11] == '=HYPERLINK("#gid=42","EICR Nov 2026")'
    assert rows[1][12] == "FALSE"


def test_black_book_newest_firm_wins_each_kind_and_preferred_fills_gaps():
    older = _closed_job()
    older.created_at = "2026-01-01T09:00:00+00:00"
    newer = _closed_job()
    newer.id, newer.chosen_supplier_id = "r-2", "s-2"
    newer.job_tab, newer.job_tab_gid = None, None
    suppliers = [
        _supplier(),
        _supplier(id="s-2", name="Beta Sparks", drive_folder_id="F1", in_xero=True),
        _supplier(id="s-3", name="Cee Plumbing", preferred=True, categories=["Plumbing"]),
    ]
    rows = black_book_rows(suppliers, [older, newer])
    assert [r[:2] for r in rows[1:]] == [
        ["Electrical", "Beta Sparks"],
        ["Plumbing", "Cee Plumbing"],
    ]
    assert rows[1][10] == '=HYPERLINK("https://drive.google.com/drive/folders/F1","folder")'
    assert rows[1][11] == "" and rows[1][12] == "TRUE"
    assert rows[2][6] == "" and rows[2][11] == ""
    assert rows[2][9] == '=IF(H3="","",H3-I3)'


def test_log_newest_first():
    r = _job("EICR Nov 2026")
    entries = [
        LogEntry(id="l1", at="2026-11-01T09:05:00+00:00", request_id=r.id, text="Rang Acme"),
        LogEntry(id="l2", at="2026-07-01T23:30:00+00:00", request_id=None, text="Housekeeping"),
        LogEntry(id="l3", at="2026-11-02T10:00:00+00:00", request_id=r.id, text="Quote in"),
    ]
    rows = log_rows(entries, {r.id: r})
    assert rows[0] == list(contract.LOG_COLUMNS)
    assert rows[1:] == [
        ["2026-11-02 10:00", "'EICR Nov 2026", "Quote in"],
        ["2026-11-01 09:05", "'EICR Nov 2026", "Rang Acme"],
        ["2026-07-02 00:30", "", "Housekeeping"],
    ]


@pytest.mark.parametrize(
    ("value", "cell"),
    [
        ("=SUM(A1)", "'=SUM(A1)"),
        ("+ve reply", "'+ve reply"),
        ("- ring after 5", "'- ring after 5"),
        ("@office", "'@office"),
        ("1/2", "'1/2"),
        ("250", "'250"),
        ("TRUE", "'TRUE"),
        ("'til Friday", "''til Friday"),
        ("Acme Testing", "Acme Testing"),
        ("", ""),
    ],
)
def test_free_text_that_sheets_would_reinterpret_is_escaped(value, cell):
    from xsource.workbook.layout import text_cell

    assert text_cell(value) == cell


def test_job_tab_free_text_is_escaped_but_prices_stay_numbers():
    r = _job_with_quote(first=78000, latest=72000, on="2026-11-05", via="email")
    r.shortlist[0].notes = "=no access before 10"
    r.shortlist[0].contact_name = "1/2 day Pat"
    rows = job_tab_rows(r, _suppliers())
    assert rows[1][2] == "'1/2 day Pat"
    assert rows[1][14] == "'=no access before 10"
    assert rows[1][9:11] == ["780", "720"]


def test_black_book_free_text_is_escaped():
    s = _supplier(contact_name="@Sam", email="+sam@example.test")
    rows = black_book_rows([s], [_closed_job()])
    assert rows[1][2] == "'@Sam" and rows[1][4] == "'+sam@example.test"
