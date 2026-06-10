from xsource.store.models import Request, ShortlistEntry, Supplier


def test_supplier_round_trip():
    s = Supplier(
        id="s-0017",
        name="Westcountry Tree Care",
        categories=["trees-grounds"],
        tags=["tree-surgery"],
        phone="+441626332000",
        email="info@wtc.co.uk",
        website="wtc.co.uk",
        address="1 High St",
        postcode="TQ12 1AA",
        place_id="ChIJx",
        rating={"google": [4.9, 31]},
        source="places",
        source_url="https://maps.google.com/x",
    )
    assert Supplier.from_dict(s.to_dict()) == s


def test_supplier_tolerates_missing_keys():
    s = Supplier.from_dict({"id": "s-1", "name": "X"})
    assert s.categories == [] and s.rating == {} and s.preferred is False
    assert s.price_history == [] and s.notes == [] and s.recurs_every_months is None


def test_request_round_trip():
    r = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="tree down",
        triage={"category": "trees-grounds"},
        constraints={"radius_miles": 15},
        status="open",
        sheet_id=None,
        sheet_url=None,
        indicative_range=None,
        shortlist=[ShortlistEntry(supplier_id="s-0017", rank=1)],
        chosen_supplier_id=None,
    )
    r2 = Request.from_dict(r.to_dict())
    assert r2 == r and r2.shortlist[0].supplier_id == "s-0017"


def test_shortlist_entry_defaults():
    e = ShortlistEntry.from_dict({"supplier_id": "s-1", "rank": 2})
    assert e.excluded is False and e.outreach == {} and e.reply == {}
