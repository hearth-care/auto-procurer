import json
from pathlib import Path

from xsource.research.places import search_places

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "places_text_search.json").read_text())


def fake_post(url, headers, json_body):
    fake_post.calls.append((url, headers, json_body))
    return FIXTURE


fake_post.calls = []


def test_search_places_maps_fields():
    cands = search_places("tree surgeon", "TQ12 4QQ", radius_miles=15, api_key="KEY", post_fn=fake_post)
    first = cands[0]
    assert first.name == "TQ Tree Services"
    assert first.phone == "+441626870111"
    assert first.website == "tqtrees.co.uk"
    assert first.rating == 4.8 and first.review_count == 57 and first.rating_scale == 5
    assert first.source == "places" and first.place_id == "ChIJabc123"


def test_missing_fields_become_none_not_guesses():
    second = search_places("tree surgeon", "TQ12 4QQ", radius_miles=15, api_key="KEY", post_fn=fake_post)[1]
    assert second.phone is None and second.website is None and second.name == "Haldon Arb Ltd"


def test_request_shape():
    url, headers, body = fake_post.calls[0]
    assert url == "https://places.googleapis.com/v1/places:searchText"
    assert headers["X-Goog-Api-Key"] == "KEY"
    assert "tree surgeon" in body["textQuery"] and "TQ12 4QQ" in body["textQuery"]
