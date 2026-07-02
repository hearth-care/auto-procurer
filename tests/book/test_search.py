from xsource.book.search import find_matches, search_suppliers
from xsource.store.models import Supplier

SUPPLIERS = [
    Supplier(
        id="s-1",
        name="Westcountry Tree Care",
        categories=["trees-grounds"],
        tags=["tree-surgery", "chipping"],
    ),
    Supplier(id="s-2", name="Smith Heating", categories=["heating"], tags=["boiler"]),
    Supplier(id="s-3", name="TQ Sparks", categories=["electrical"], tags=[]),
]


def test_find_matches_by_category():
    assert [s.id for s in find_matches(SUPPLIERS, category="trees-grounds", tags=[])] == ["s-1"]


def test_find_matches_by_tag_overlap():
    assert [s.id for s in find_matches(SUPPLIERS, category="other", tags=["chipping"])] == ["s-1"]


def test_no_matches_is_empty_not_error():
    assert find_matches(SUPPLIERS, category="roofing", tags=["slate"]) == []


def test_search_by_name_substring_case_insensitive():
    assert [s.id for s in search_suppliers(SUPPLIERS, "smith")] == ["s-2"]
    assert [s.id for s in search_suppliers(SUPPLIERS, "tree")] == ["s-1"]


def test_search_by_category_and_tag():
    assert [s.id for s in search_suppliers(SUPPLIERS, "heating")] == ["s-2"]
    assert [s.id for s in search_suppliers(SUPPLIERS, "boiler")] == ["s-2"]
