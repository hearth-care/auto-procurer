from __future__ import annotations

import base64
from email import message_from_bytes

from xsource.config import Config
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


def _from_header(service):
    raw = service.drafts.created[0]["body"]["message"]["raw"]
    return message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))["From"]


def _draft(service):
    SafeOutreachClient(service, Config.from_env().mail_identity()).create_draft(
        to="quotes@example.com", subject="Quote", body="Hello", label="xsource/outbox"
    )


def test_from_header_follows_mailbox_env(monkeypatch):
    monkeypatch.setenv("XSOURCE_MAILBOX_ADDRESS", "gareth@example.com")
    monkeypatch.setenv("XSOURCE_MAILBOX_DISPLAY_NAME", "Gareth Exampleton")
    service = _Service()
    _draft(service)
    assert _from_header(service) == "Gareth Exampleton <gareth@example.com>"


def test_from_display_name_falls_back_to_operator_name(monkeypatch):
    monkeypatch.delenv("XSOURCE_MAILBOX_DISPLAY_NAME", raising=False)
    monkeypatch.setenv("XSOURCE_MAILBOX_ADDRESS", "gareth@example.com")
    monkeypatch.setenv("XSOURCE_OPERATOR_DISPLAY_NAME", "Jane")
    service = _Service()
    _draft(service)
    assert _from_header(service) == "Jane <gareth@example.com>"


def test_create_draft_posts_to_gmail_drafts_only(monkeypatch):
    monkeypatch.setenv("XSOURCE_MAILBOX_ADDRESS", "gareth@example.com")
    monkeypatch.setenv("XSOURCE_MAILBOX_DISPLAY_NAME", "Gareth")
    service = _Service()
    client = SafeOutreachClient(service, Config.from_env().mail_identity())

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
    assert mime["From"] == "Gareth <gareth@example.com>"
    assert mime["To"] == "quotes@example.com"
    assert mime["Subject"] == "Tree chipping quote"
    assert "ref r-0042" in mime.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "labelIds" not in created["body"]["message"]


def test_safe_outreach_client_has_no_send_method():
    assert not hasattr(SafeOutreachClient, "send")
    assert not hasattr(SafeOutreachClient, "send_message")
