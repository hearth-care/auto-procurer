"""Google Places API (New) text search."""

from __future__ import annotations

import math
from urllib.parse import quote, urlparse

from xsource.research.candidates import Candidate
from xsource.research.phones import normalise_uk_phone

_URL = "https://places.googleapis.com/v1/places:searchText"
_POSTCODE_URL = "https://api.postcodes.io/postcodes/"
_MILES_PER_DEGREE_LAT = 69.0
_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.formattedAddress",
        "places.location",
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


def real_geocode(postcode: str) -> tuple[float, float]:
    import requests

    response = requests.get(_POSTCODE_URL + quote(postcode), timeout=20)
    response.raise_for_status()
    result = response.json()["result"]
    return float(result["latitude"]), float(result["longitude"])


def _miles_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def _radius_box(home: tuple[float, float], radius_miles: int) -> dict:
    lat, lng = home
    dlat = radius_miles / _MILES_PER_DEGREE_LAT
    dlng = radius_miles / (_MILES_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    return {
        "rectangle": {
            "low": {"latitude": lat - dlat, "longitude": lng - dlng},
            "high": {"latitude": lat + dlat, "longitude": lng + dlng},
        }
    }


def search_places(
    term: str,
    home_postcode: str,
    radius_miles: int,
    api_key: str,
    post_fn=real_post,
    geocode_fn=real_geocode,
) -> list[Candidate]:
    # A text query alone lets Google return firms 100 miles away, so the search is
    # restricted to a box around home and the box corners are trimmed back to the radius.
    home = geocode_fn(home_postcode)
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _FIELD_MASK}
    body = {"textQuery": term, "locationRestriction": _radius_box(home, radius_miles)}
    data = post_fn(_URL, headers, body)
    out: list[Candidate] = []
    for place in data.get("places", []):
        location = place.get("location") or {}
        if "latitude" not in location:
            continue
        miles = _miles_between(home, (location["latitude"], location["longitude"]))
        if miles > radius_miles:
            continue
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
                extra={"miles": round(miles, 1)},
            )
        )
    return out
