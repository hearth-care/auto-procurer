"""Google Places API (New) text search."""

from __future__ import annotations

from urllib.parse import urlparse

from xsource.research.candidates import Candidate
from xsource.research.phones import normalise_uk_phone

_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
    ]
)


def real_post(url: str, headers: dict, json_body: dict) -> dict:
    import requests

    response = requests.post(url, headers=headers, json=json_body, timeout=20)
    response.raise_for_status()
    return response.json()


def _domain(uri: str | None) -> str | None:
    if not uri:
        return None
    netloc = urlparse(uri).netloc.lower()
    return netloc.removeprefix("www.") or None


def search_places(
    term: str,
    home_postcode: str,
    radius_miles: int,
    api_key: str,
    post_fn=real_post,
) -> list[Candidate]:
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _FIELD_MASK}
    body = {"textQuery": f"{term} near {home_postcode}"}
    data = post_fn(_URL, headers, body)
    out: list[Candidate] = []
    for place in data.get("places", []):
        place_id = place.get("id")
        out.append(
            Candidate(
                name=place.get("displayName", {}).get("text", "").strip() or "(unnamed)",
                source="places",
                source_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                if place_id
                else None,
                phone=normalise_uk_phone(place.get("nationalPhoneNumber") or ""),
                website=_domain(place.get("websiteUri")),
                address=place.get("formattedAddress"),
                place_id=place_id,
                rating=place.get("rating"),
                review_count=place.get("userRatingCount"),
                rating_scale=5 if place.get("rating") is not None else None,
            )
        )
    return out
