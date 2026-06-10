from __future__ import annotations

import base64
from email import message_from_bytes

from xsource.outreach.client import SafeOutreachClient


class _Executable:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Drafts:
    def __init__(self):
        self.created = []

    def create(self, *, userId, body):
        self.created.append({"userId": userId, "body": body})
        return _Executable({"id": "draft-123", "message": {"id": "msg-123", "threadId": "thr-123"}})


class _Users:
    def __init__(self, drafts):
        self._drafts = drafts

    def drafts(self):
        return self._drafts


class _Service:
    def __init__(self):
        self.drafts = _Drafts()

    def users(self):
        return _Users(self.drafts)


def test_create_draft_posts_to_gmail_drafts_only():
    service = _Service()
    client = SafeOutreachClient(service)

    result = client.create_draft(
        to="quotes@example.com",
        subject="Tree chipping quote",
        body="Hello\n\nCould you quote for tree chipping?\n\nref r-0042",
        label="xsource/outbox",
    )

    assert result == {"draft_id": "draft-123", "message_id": "msg-123", "thread_id": "thr-123"}
    assert len(service.drafts.created) == 1
    created = service.drafts.created[0]
    assert created["userId"] == "me"
    raw = created["body"]["message"]["raw"]
    mime = message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))
    assert mime["To"] == "quotes@example.com"
    assert mime["Subject"] == "Tree chipping quote"
    assert "ref r-0042" in mime.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert created["body"]["message"]["labelIds"] == ["xsource/outbox"]


def test_safe_outreach_client_has_no_send_method():
    assert not hasattr(SafeOutreachClient, "send")
    assert not hasattr(SafeOutreachClient, "send_message")
