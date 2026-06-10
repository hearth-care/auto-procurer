"""Companies House cross-check."""

from __future__ import annotations

import logging

log = logging.getLogger("xsource.research")

_URL = "https://api.company-information.service.gov.uk/search/companies"


def real_get(url: str, params: dict, auth: tuple) -> dict:
    import requests

    response = requests.get(url, params=params, auth=auth, timeout=15)
    response.raise_for_status()
    return response.json()


def company_check(name: str, api_key: str, get_fn=real_get) -> dict | None:
    try:
        data = get_fn(_URL, {"q": name, "items_per_page": 1}, (api_key, ""))
    except Exception as exc:
        log.warning("companies house check failed for %r: %s", name, exc)
        return None
    items = data.get("items") or []
    if not items:
        return None
    top = items[0]
    if top.get("title", "").lower().rstrip(" ltd")[:12] != name.lower()[:12]:
        return None
    return {
        "number": top.get("company_number"),
        "status": top.get("company_status"),
        "incorporated": top.get("date_of_creation"),
    }
