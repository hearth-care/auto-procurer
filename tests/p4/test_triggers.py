from __future__ import annotations

from xsource.p4.triggers import parse_trigger


def test_parse_email_trigger_extracts_request_need():
    trigger = parse_trigger(
        {
            "source": "email",
            "subject": "Need supplier help",
            "body": "Please find someone for tree chipping near Newton Abbot by Friday.",
        }
    )

    assert trigger.kind == "request.new"
    assert trigger.raw_need == "Please find someone for tree chipping near Newton Abbot by Friday."
    assert trigger.constraints == {"source": "email"}


def test_parse_chat_trigger_ignores_non_procurement_text():
    trigger = parse_trigger({"source": "chat", "body": "Thanks, all sorted."})

    assert trigger is None
