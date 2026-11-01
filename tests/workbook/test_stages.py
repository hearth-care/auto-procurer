import datetime as dt

from xsource.store.models import Request, ShortlistEntry
from xsource.workbook.stages import advance, record_price


def _request(stages, job_stage="Searching", **kw):
    return Request(
        id="r-1",
        created_at="2026-11-01T09:00:00+00:00",
        raw_need="a plumber",
        stage=job_stage,
        shortlist=[
            ShortlistEntry(supplier_id=f"s-{i}", rank=i, stage=s) for i, s in enumerate(stages, 1)
        ],
        **kw,
    )


def test_new_job_is_calling_with_firms_to_ring():
    r = _request(stages=["To call", "To call", "To call"])
    assert advance(r) == ["Stage: Searching → Calling"]
    assert r.next_step == "Ring 3 firms on the call list"
    assert r.waiting_on == "You: ring 3 firms"


def test_any_emailed_firm_moves_job_to_waiting_for_prices():
    r = _request(stages=["Emailed", "No answer", "Declined"], job_stage="Calling")
    advance(r)
    assert r.stage == "Waiting for prices" and r.waiting_on == "Nobody"
    assert r.next_step == "Wait for prices (0 of 1 in)"


def test_booked_firm_marks_others_not_chosen_and_job_booked():
    r = _request(stages=["Booked", "Quoted", "Keen"], job_stage="Waiting for prices")
    advance(r)
    assert [e.stage for e in r.shortlist] == ["Booked", "Not chosen", "Not chosen"]
    assert r.stage == "Booked"


def test_booked_keeps_declined_and_names_the_firm():
    r = _request(stages=["Declined", "Booked", "Emailed"], job_stage="Waiting for prices")
    advance(r, names={"s-2": "Acme Plumbing"})
    assert [e.stage for e in r.shortlist] == ["Declined", "Booked", "Not chosen"]
    assert r.next_step == "Confirm the date with Acme Plumbing"
    assert r.waiting_on == "You: confirm the date"


def test_booked_falls_back_to_supplier_id_when_name_missing():
    r = _request(stages=["Booked"], job_stage="Booked")
    advance(r)
    assert r.next_step == "Confirm the date with s-1"


def test_first_price_is_kept_when_a_better_price_arrives():
    e = ShortlistEntry(supplier_id="s-1", rank=1)
    record_price(e, 78000, on=dt.date(2026, 11, 2), via="email")
    record_price(e, 72000, on=dt.date(2026, 11, 5), via="email")
    assert (e.first_price_minor, e.latest_price_minor) == (78000, 72000)
    assert e.last_contact == {"date": "2026-11-05", "via": "email"}
    assert e.stage == "Quoted"


def test_advance_twice_logs_nothing_the_second_time():
    r = _request(stages=["To call"])
    advance(r)
    assert advance(r) == []


def test_quotes_in_count_shows_in_next_step():
    r = _request(stages=["Quoted", "Emailed", "Emailed"], job_stage="Waiting for prices")
    advance(r)
    assert r.next_step == "Wait for prices (1 of 3 in)"


def test_haggling_is_left_alone_until_a_firm_is_booked():
    r = _request(stages=["Quoted", "Quoted"], job_stage="Haggling")
    assert advance(r) == []
    assert r.stage == "Haggling"
    r.shortlist[0].stage = "Booked"
    assert advance(r) == ["Stage: Haggling → Booked"]


def test_closed_request_is_done():
    r = _request(stages=["Quoted"], job_stage="Waiting for prices", status="closed")
    assert advance(r) == ["Stage: Waiting for prices → Done"]
    assert (r.stage, r.next_step, r.waiting_on) == ("Done", "", "Nobody")
