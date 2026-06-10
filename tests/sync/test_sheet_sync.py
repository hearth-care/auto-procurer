from __future__ import annotations

import datetime as dt

from xsource.sheet.sync import apply_sheet_rows
from xsource.store.models import Request, ShortlistEntry, Supplier


class _Store:
    def __init__(self, records):
        self.records = {record.id: record for record in records}
        self.upserted = []

    def get(self, rec_id):
        return self.records.get(rec_id)

    def upsert(self, rec):
        self.records[rec.id] = rec
        self.upserted.append(rec)


def test_apply_sheet_rows_closes_chosen_request_and_updates_price_history():
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        status="open",
        shortlist=[
            ShortlistEntry(supplier_id="s-1", rank=1),
            ShortlistEntry(supplier_id="s-2", rank=2),
        ],
    )
    suppliers = _Store(
        [
            Supplier(id="s-1", name="Winner"),
            Supplier(id="s-2", name="Quoted loser"),
        ]
    )
    rows = [
        {"rank": 1, "chosen": "yes", "quote": "185", "status": "Chosen", "notes": "good"},
        {"rank": 2, "chosen": "", "quote": "220", "status": "Quoted", "notes": "more expensive"},
    ]

    report = apply_sheet_rows(
        request,
        rows,
        suppliers=suppliers,
        synced_at=dt.datetime(2026, 6, 12, 8, 0, tzinfo=dt.UTC),
    )

    assert report == {"updated_suppliers": 2, "warnings": []}
    assert request.status == "closed"
    assert request.chosen_supplier_id == "s-1"
    winner = suppliers.get("s-1")
    loser = suppliers.get("s-2")
    assert winner.last_used == "2026-06-12"
    assert winner.price_history[-1]["outcome"] == "used"
    assert winner.price_history[-1]["amount"] == 185
    assert loser.price_history[-1]["outcome"] == "quoted"
    assert loser.notes[-1]["text"] == "more expensive"


def test_apply_sheet_rows_warns_unknown_rank_without_crashing():
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+00:00",
        raw_need="tree chipping",
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],
    )
    suppliers = _Store([Supplier(id="s-1", name="Known")])

    report = apply_sheet_rows(
        request,
        [{"rank": 99, "chosen": "yes"}],
        suppliers=suppliers,
        synced_at=dt.datetime(2026, 6, 12, 8, 0, tzinfo=dt.UTC),
    )

    assert report == {"updated_suppliers": 0, "warnings": ["unknown rank 99"]}
    assert request.status == "open"
