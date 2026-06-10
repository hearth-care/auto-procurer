"""Turn a plain-English need into a search plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "search_terms": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "also_try": {"type": "array", "items": {"type": "string"}},
        "email_vars": {
            "type": "object",
            "properties": {
                "job_summary": {"type": "string"},
                "location_town": {"type": "string"},
            },
            "required": ["job_summary", "location_town"],
        },
    },
    "required": ["category", "search_terms", "also_try", "email_vars"],
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "search_terms": self.search_terms,
            "also_try": self.also_try,
            "email_vars": self.email_vars,
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
            search_terms=[str(x) for x in out["search_terms"]],
            also_try=[str(x) for x in out.get("also_try", [])],
            email_vars={k: str(v) for k, v in out["email_vars"].items()},
        )
    except (KeyError, TypeError) as exc:
        raise TriageError(f"triage output missing/invalid field: {exc}") from exc
    if not triage.search_terms:
        raise TriageError("triage produced no search terms")
    return triage
