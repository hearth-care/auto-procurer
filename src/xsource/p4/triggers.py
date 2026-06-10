"""Parse lightweight email/chat triggers into request.new input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_PROCUREMENT_HINTS = (
    "find someone",
    "supplier",
    "quote",
    "procure",
    "contractor",
    "trades",
    "repair",
    "chipping",
)


@dataclass(frozen=True)
class ParsedTrigger:
    kind: str
    raw_need: str
    constraints: dict[str, Any]


def parse_trigger(payload: dict[str, Any]) -> ParsedTrigger | None:
    body = str(payload.get("body") or "").strip()
    if not body:
        return None
    haystack = f"{payload.get('subject', '')} {body}".lower()
    if not any(hint in haystack for hint in _PROCUREMENT_HINTS):
        return None
    return ParsedTrigger(
        kind="request.new",
        raw_need=body,
        constraints={"source": str(payload.get("source") or "unknown")},
    )
