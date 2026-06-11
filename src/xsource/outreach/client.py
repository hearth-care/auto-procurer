"""Safe Gmail draft client for supplier outreach.

This is deliberately draft-only. xsource never sends supplier email in P2.
"""

from __future__ import annotations

import base64
from email.errors import HeaderParseError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from clonway_cockpit.mail_identity import MailIdentity, format_from_header

_MILO_GARTH_IDENTITY = MailIdentity(
    address="milo.garth@clonwaycare.co.uk",
    display_name="Milo Garth",
    source="xsource.outreach",
)


class OutreachDraftBlocked(RuntimeError):
    """Raised when a draft request violates xsource's safety invariants."""


class SafeOutreachClient:
    """The only xsource wrapper around the Gmail service for outreach.

    It exposes draft creation only. The structural no-send test catches send
    endpoints anywhere in ``src/xsource``.
    """

    def __init__(self, service: Any) -> None:
        self.__service = service

    def create_draft(self, *, to: str, subject: str, body: str, label: str) -> dict[str, str]:
        if not to or "@" not in to:
            raise OutreachDraftBlocked("refusing to create draft without supplier email")
        if not subject.strip():
            raise OutreachDraftBlocked("refusing to create draft without subject")
        if not body.strip():
            raise OutreachDraftBlocked("refusing to create draft without body")

        try:
            mime = MIMEMultipart("alternative")
            mime["From"] = format_from_header(_MILO_GARTH_IDENTITY)
            mime["To"] = to
            mime["Subject"] = subject
            mime.attach(MIMEText(body, "plain", _charset="utf-8"))
            html = "".join(f"<p>{line}</p>" for line in body.split("\n\n") if line.strip())
            mime.attach(MIMEText(f"<html><body>{html}</body></html>", "html", _charset="utf-8"))
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
            payload = {"message": {"raw": raw, "labelIds": [label]}}
            created = (
                self.__service.users()
                .drafts()
                .create(
                    userId="me",
                    body=payload,
                )
                .execute()
            )
        except HeaderParseError as exc:
            raise OutreachDraftBlocked(f"refusing malformed draft headers: {exc}") from exc

        message = created.get("message", {})
        return {
            "draft_id": created.get("id", ""),
            "message_id": message.get("id", ""),
            "thread_id": message.get("threadId", ""),
        }
