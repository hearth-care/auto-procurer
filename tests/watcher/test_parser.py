from __future__ import annotations

import pytest

from xsource.watcher.parser import ReplyParseError, parse_supplier_reply


class _Gateway:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete_structured(self, messages, schema, role="research"):
        self.calls.append({"messages": messages, "schema": schema, "role": role})
        return self.result


def test_parse_supplier_reply_accepts_quote_with_source_span():
    gateway = _Gateway(
        {
            "quote_amount": 185,
            "currency": "GBP",
            "includes": "cut and chip",
            "availability": "Thursday",
            "conditions": None,
            "declined": False,
            "summary": "Quoted £185 and can attend Thursday.",
            "source_span": "£185 including cutting and chipping",
        }
    )

    parsed = parse_supplier_reply("We can do it for £185 including cutting and chipping.", gateway)

    assert parsed.status == "quoted"
    assert parsed.quote_amount == 185
    assert parsed.source_span == "£185 including cutting and chipping"
    assert gateway.calls[0]["role"] == "watcher"


def test_parse_supplier_reply_rejects_quote_without_source_span():
    gateway = _Gateway(
        {
            "quote_amount": 185,
            "currency": "GBP",
            "includes": None,
            "availability": None,
            "conditions": None,
            "declined": False,
            "summary": "Quoted £185.",
            "source_span": "",
        }
    )

    with pytest.raises(ReplyParseError, match="source span"):
        parse_supplier_reply("Looks fine.", gateway)


def test_parse_supplier_reply_maps_decline_to_no():
    gateway = _Gateway(
        {
            "quote_amount": None,
            "currency": "GBP",
            "includes": None,
            "availability": None,
            "conditions": "too busy",
            "declined": True,
            "summary": "Declined because they are too busy.",
            "source_span": None,
        }
    )

    parsed = parse_supplier_reply("Sorry, we are too busy.", gateway)

    assert parsed.status == "no"
    assert parsed.quote_amount is None
