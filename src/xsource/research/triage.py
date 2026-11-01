"""Turn a plain-English need into a search plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Google Places business types for local trades; the Maps search is held to the chosen one
# so a request for an electrician cannot come back as a well-reviewed plumber.
PLACE_TYPES = [
    "electrician",
    "plumber",
    "roofing_contractor",
    "painter",
    "locksmith",
    "moving_company",
    "general_contractor",
]

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "short_label": {
            "type": "string",
            "maxLength": 20,
            "description": "A tab label of at most 20 characters, e.g. EICR.",
        },
        "search_terms": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "also_try": {"type": "array", "items": {"type": "string"}},
        "place_type": {
            "type": ["string", "null"],
            "enum": [*PLACE_TYPES, None],
            "description": "The Google Maps business type for this trade, or null if none fits.",
        },
        "email_vars": {
            "type": "object",
            "properties": {
                "job_summary": {"type": "string"},
                "location_town": {"type": "string"},
            },
            "required": ["job_summary", "location_town"],
        },
    },
    "required": ["category", "short_label", "search_terms", "also_try", "place_type", "email_vars"],
}

_SYSTEM = (
    "You turn a small-business owner's plain-English procurement need into a search plan "
    "for finding LOCAL UK tradespeople or hire services. Output strictly to the schema."
)


@dataclass(frozen=True)
class Triage:
    category: str
    search_terms: list[str]
    also_try: list[str]
    email_vars: dict[str, str]
    place_type: str | None = None
    short_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "search_terms": self.search_terms,
            "also_try": self.also_try,
            "email_vars": self.email_vars,
            "place_type": self.place_type,
            "short_label": self.short_label,
        }


class TriageError(RuntimeError):
    """Malformed triage output."""


def run_triage(raw_need: str, constraints: dict[str, Any], gateway) -> Triage:
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Need: {raw_need}\nConstraints: {constraints}"},
    ]
    out = gateway.complete_structured(messages, TRIAGE_SCHEMA, role="research")
    try:
        triage = Triage(
            category=str(out["category"]),
            short_label=str(out.get("short_label") or "")[:20],
            search_terms=[str(x) for x in out["search_terms"]],
            also_try=[str(x) for x in out.get("also_try", [])],
            email_vars={k: str(v) for k, v in out["email_vars"].items()},
            place_type=out.get("place_type") if out.get("place_type") in PLACE_TYPES else None,
        )
    except (KeyError, TypeError) as exc:
        raise TriageError(f"triage output missing/invalid field: {exc}") from exc
    if not triage.search_terms:
        raise TriageError("triage produced no search terms")
    return triage
