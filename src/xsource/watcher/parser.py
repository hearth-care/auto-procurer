"""Structured supplier reply parsing with no-fabricated-quote enforcement."""

from __future__ import annotations

from dataclasses import dataclass

_REPLY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "quote_amount",
        "currency",
        "includes",
        "availability",
        "conditions",
        "declined",
        "summary",
        "source_span",
    ],
    "properties": {
        "quote_amount": {"type": ["number", "null"]},
        "currency": {"type": "string"},
        "includes": {"type": ["string", "null"]},
        "availability": {"type": ["string", "null"]},
        "conditions": {"type": ["string", "null"]},
        "declined": {"type": "boolean"},
        "summary": {"type": "string"},
        "source_span": {"type": ["string", "null"]},
    },
}


class ReplyParseError(RuntimeError):
    """Raised when structured reply extraction violates safety invariants."""


@dataclass(frozen=True)
class ParsedReply:
    status: str
    quote_amount: int | None
    currency: str
    includes: str | None
    availability: str | None
    conditions: str | None
    declined: bool
    summary: str
    source_span: str | None


def parse_supplier_reply(body: str, gateway) -> ParsedReply:
    result = gateway.complete_structured(
        [
            {
                "role": "user",
                "content": (
                    "Extract the supplier reply. Quote amount may be set only when "
                    "the reply contains a verbatim span proving the amount.\n\n"
                    f"Reply:\n{body}"
                ),
            }
        ],
        _REPLY_SCHEMA,
        role="watcher",
    )
    quote_amount = result.get("quote_amount")
    source_span = result.get("source_span")
    if quote_amount is not None and not str(source_span or "").strip():
        raise ReplyParseError("quote amount requires a verbatim source span")
    declined = bool(result.get("declined"))
    status = "no" if declined else "quoted" if quote_amount is not None else "replied"
    return ParsedReply(
        status=status,
        quote_amount=int(quote_amount) if quote_amount is not None else None,
        currency=str(result.get("currency") or "GBP"),
        includes=result.get("includes"),
        availability=result.get("availability"),
        conditions=result.get("conditions"),
        declined=declined,
        summary=str(result.get("summary") or "").strip(),
        source_span=str(source_span).strip() if source_span else None,
    )
