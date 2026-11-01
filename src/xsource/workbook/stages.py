from __future__ import annotations

import datetime as dt
from collections.abc import Mapping

from xsource.store.models import Request, ShortlistEntry


def record_price(entry: ShortlistEntry, amount_minor: int, *, on: dt.date, via: str) -> None:
    if entry.first_price_minor is None:
        entry.first_price_minor = amount_minor
    entry.latest_price_minor = amount_minor
    entry.stage = "Quoted"
    entry.last_contact = {"date": on.isoformat(), "via": via}


def advance(request: Request, *, names: Mapping[str, str] | None = None) -> list[str]:
    old_stage = request.stage
    entries = request.shortlist
    booked = next((e for e in entries if e.stage == "Booked"), None)

    if request.status == "closed":
        stage, next_step, waiting_on = "Done", "", "Nobody"
    elif booked is not None:
        for e in entries:
            if e is not booked and e.stage not in ("Declined", "Not chosen"):
                e.stage = "Not chosen"
        firm = (names or {}).get(booked.supplier_id, booked.supplier_id)
        stage = "Booked"
        next_step, waiting_on = f"Confirm the date with {firm}", "You: confirm the date"
    elif any(e.stage in ("Emailed", "Quoted") for e in entries):
        asked = sum(e.stage in ("Emailed", "Quoted") for e in entries)
        in_ = sum(e.stage == "Quoted" for e in entries)
        # Haggling is entered by the negotiation step, not derived from firm stages.
        stage = "Haggling" if old_stage == "Haggling" else "Waiting for prices"
        next_step, waiting_on = f"Wait for prices ({in_} of {asked} in)", "Nobody"
    elif old_stage == "Haggling":
        stage, next_step, waiting_on = old_stage, request.next_step, request.waiting_on
    else:
        n = sum(e.stage in ("To call", "No answer") for e in entries)
        noun = "firm" if n == 1 else "firms"
        stage = "Calling"
        next_step, waiting_on = f"Ring {n} {noun} on the call list", f"You: ring {n} {noun}"

    request.stage, request.next_step, request.waiting_on = stage, next_step, waiting_on
    return [f"Stage: {old_stage} → {stage}"] if stage != old_stage else []
