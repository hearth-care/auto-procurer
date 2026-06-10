import json
from pathlib import Path

from xsource.research.candidates import Candidate
from xsource.sheet.template import COLUMNS, STATUS_VALUES, build_values

GOLDEN = Path(__file__).parent / "golden_values.json"


def fixture_rows():
    return [
        Candidate(
            name="Westcountry Tree Care",
            source="book",
            phone="+441626332000",
            email="info@wtc.co.uk",
            rating=4.9,
            review_count=31,
            rating_scale=5,
            source_url="https://wtc.example",
        ),
        Candidate(
            name="D. Mortimer Tree Work",
            source="yell",
            phone="+447712901234",
            rating=4.6,
            review_count=9,
            rating_scale=5,
            source_url="https://yell.com/biz/dm",
        ),
        Candidate(
            name="Teign Trees & Grounds",
            source="checkatrade",
            rating=9.4,
            review_count=12,
            rating_scale=10,
            source_url="https://checkatrade.com/t",
        ),
    ]


def test_columns_are_the_spec_contract():
    assert COLUMNS == [
        "#",
        "Provider",
        "Source",
        "Rating",
        "Phone",
        "Email",
        "Indicative",
        "Status",
        "Asked",
        "Reply",
        "Quote £",
        "Chosen",
        "Updated",
        "Notes",
    ]
    assert STATUS_VALUES == ["To call", "Draft ready", "Asked", "Replied", "Quoted", "Chosen", "No"]


def test_values_grid_matches_golden():
    values = build_values(
        request_id="r-0042",
        job_line="fallen tree, cut/chip/remove · Rowan House, TQ12 · needed by Fri 13 Jun",
        indicative={"low": 150, "high": 400, "sources": 3},
        rows=fixture_rows(),
        indicatives=[[150, 250], None, None],
        now_label="10 Jun 15:58",
    )
    expected = json.loads(GOLDEN.read_text())
    assert values == expected


def test_phone_first_rows_get_to_call_status():
    values = build_values("r-1", "job", None, fixture_rows(), [None, None, None], "10 Jun 15:58")
    statuses = [row[7] for row in values[1:4]]
    assert statuses == ["To call", "To call", "To call"]
