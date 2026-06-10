"""Checkatrade partner lead request construction.

This module builds signed requests only. Posting a lead is a real-world write
and must stay behind the cockpit apply gate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckatradeLead:
    request_id: str
    category: str
    postcode: str
    description: str
    contact_name: str
    contact_email: str

    def validate(self) -> list[str]:
        missing = []
        for field in (
            "request_id",
            "category",
            "postcode",
            "description",
            "contact_name",
            "contact_email",
        ):
            if not str(getattr(self, field)).strip():
                missing.append(f"{field} missing")
        return missing


@dataclass(frozen=True)
class SignedLeadRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: dict[str, str]


class CheckatradeLeadClient:
    def __init__(self, *, partner_id: str, secret: str) -> None:
        self.partner_id = partner_id
        self.secret = secret

    def build_request(self, lead: CheckatradeLead) -> SignedLeadRequest:
        errors = lead.validate()
        if errors:
            raise ValueError(", ".join(errors))
        body = {
            "external_ref": lead.request_id,
            "category": lead.category,
            "postcode": lead.postcode,
            "description": lead.description,
            "contact_name": lead.contact_name,
            "contact_email": lead.contact_email,
        }
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(
            self.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return SignedLeadRequest(
            method="POST",
            path="/jobs",
            headers={"X-Partner-Id": self.partner_id, "X-Signature": signature},
            body=body,
        )
