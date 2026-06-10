from __future__ import annotations

import base64
import datetime as dt

from xsource.watcher.gmail import GmailWatcherClient


class _Exec:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


def _message(message_id, thread_id, from_addr, body, internal_ms=1781168400000):
    encoded = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii")
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": str(internal_ms),
        "payload": {
            "headers": [{"name": "From", "value": from_addr}],
            "parts": [{"mimeType": "text/plain", "body": {"data": encoded}}],
        },
    }


class _Threads:
    def __init__(self, payload):
        self.payload = payload

    def get(self, **kwargs):
        return _Exec(self.payload[kwargs["id"]])


class _Messages:
    def __init__(self, payload):
        self.payload = payload
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return _Exec({"messages": [{"id": message_id} for message_id in self.payload]})

    def get(self, **kwargs):
        return _Exec(self.payload[kwargs["id"]])


class _Users:
    def __init__(self, threads, messages):
        self._threads = threads
        self._messages = messages

    def threads(self):
        return self._threads

    def messages(self):
        return self._messages


class _Service:
    def __init__(self, threads_payload, messages_payload):
        self.messages_obj = _Messages(messages_payload)
        self.users_obj = _Users(_Threads(threads_payload), self.messages_obj)

    def users(self):
        return self.users_obj


def test_list_thread_messages_decodes_plain_text_and_outbound_status():
    msg = _message("m-1", "thr-1", "Milo <milo.garth@clonwaycare.co.uk>", "Hello")
    service = _Service({"thr-1": {"messages": [msg]}}, {})
    client = GmailWatcherClient(service, own_addresses={"milo.garth@clonwaycare.co.uk"})

    out = client.list_thread_messages("thr-1")

    assert len(out) == 1
    assert out[0].body == "Hello"
    assert out[0].from_addr == "milo.garth@clonwaycare.co.uk"
    assert out[0].received_at == dt.datetime(2026, 6, 11, 9, 0, tzinfo=dt.UTC)
    assert out[0].is_outbound is True


def test_list_recent_messages_fetches_full_messages():
    msg = _message("m-2", "thr-2", "supplier@example.com", "Separate reply")
    service = _Service({}, {"m-2": msg})
    client = GmailWatcherClient(service, own_addresses={"milo.garth@clonwaycare.co.uk"})

    out = client.list_recent_messages()

    assert out[0].id == "m-2"
    assert out[0].body == "Separate reply"
    assert service.messages_obj.list_calls[0]["q"] == "newer_than:7d"
