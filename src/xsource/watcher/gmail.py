"""Gmail read adapter for xsource's thread-bounded watcher."""

from __future__ import annotations

import base64
import datetime as dt
from email.utils import parseaddr
from typing import Any

from xsource.watcher.daemon import WatcherMessage


def _header(payload: dict[str, Any], name: str) -> str:
    for header in payload.get("headers", []):
        if header.get("name", "").lower() == name.lower():
            return str(header.get("value", ""))
    return ""


def _body(payload: dict[str, Any]) -> str:
    parts = payload.get("parts") or [payload]
    for part in parts:
        if part.get("mimeType") != "text/plain":
            continue
        data = part.get("body", {}).get("data")
        if not data:
            continue
        return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8")
    return ""


def _received_at(message: dict[str, Any]) -> dt.datetime:
    internal = int(message.get("internalDate") or 0) / 1000
    return dt.datetime.fromtimestamp(internal, tz=dt.UTC)


def _from_addr(payload: dict[str, Any]) -> str:
    _, addr = parseaddr(_header(payload, "From"))
    return addr.lower()


class GmailWatcherClient:
    def __init__(self, service, *, own_addresses: set[str]) -> None:
        self.service = service
        self.own_addresses = {address.lower() for address in own_addresses}

    def _convert(self, message: dict[str, Any]) -> WatcherMessage:
        payload = message.get("payload", {})
        from_addr = _from_addr(payload)
        return WatcherMessage(
            id=message["id"],
            thread_id=message["threadId"],
            from_addr=from_addr,
            body=_body(payload),
            received_at=_received_at(message),
            is_outbound=from_addr in self.own_addresses,
        )

    def list_thread_messages(self, thread_id: str) -> list[WatcherMessage]:
        thread = (
            self.service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        return [self._convert(message) for message in thread.get("messages", [])]

    def list_recent_messages(self, *, query: str = "newer_than:7d") -> list[WatcherMessage]:
        listed = self.service.users().messages().list(userId="me", q=query).execute()
        out = []
        for ref in listed.get("messages", []):
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="full")
                .execute()
            )
            out.append(self._convert(msg))
        return out

