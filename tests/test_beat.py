"""Tests for xsource.beat — GCS heartbeat writer."""

from __future__ import annotations

import json

import pytest

import xsource.beat as beat_module
from xsource.beat import write_heartbeat


class _FakeBlob:
    def __init__(self, store: dict, path: str) -> None:
        self._store = store
        self._path = path

    def upload_from_string(self, body: str, content_type: str = "") -> None:
        self._store[self._path] = body


class _FakeBucket:
    def __init__(self, store: dict) -> None:
        self._store = store

    def blob(self, path: str) -> _FakeBlob:
        return _FakeBlob(self._store, path)


class _FakeClient:
    def __init__(self, store: dict) -> None:
        self._store = store

    def bucket(self, _name: str) -> _FakeBucket:
        return _FakeBucket(self._store)


@pytest.fixture()
def gcs_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Patch xsource.beat._storage_client to return an in-memory fake."""
    store: dict[str, str] = {}
    monkeypatch.setattr(beat_module, "_storage_client", lambda: _FakeClient(store))
    return store


# ---------------------------------------------------------------------------
# Happy-path: correct job_id written, correct blob path
# ---------------------------------------------------------------------------


def test_watcher_heartbeat_ok(gcs_store):
    result = write_heartbeat("xsource.watcher", ok=True, detail="processed=3")
    assert result is True
    blob_path = "heartbeats/xsource.watcher/latest.json"
    assert blob_path in gcs_store
    payload = json.loads(gcs_store[blob_path])
    assert payload["job_id"] == "xsource.watcher"
    assert payload["ok"] is True
    assert payload["detail"] == "processed=3"


def test_sync_heartbeat_ok(gcs_store):
    result = write_heartbeat("xsource.sync", ok=True, detail="synced_requests=4")
    assert result is True
    blob_path = "heartbeats/xsource.sync/latest.json"
    assert blob_path in gcs_store
    payload = json.loads(gcs_store[blob_path])
    assert payload["job_id"] == "xsource.sync"
    assert payload["ok"] is True


def test_signals_heartbeat_ok(gcs_store):
    result = write_heartbeat("xsource.signals", ok=True, detail="emitted=2")
    assert result is True
    blob_path = "heartbeats/xsource.signals/latest.json"
    assert blob_path in gcs_store
    payload = json.loads(gcs_store[blob_path])
    assert payload["job_id"] == "xsource.signals"
    assert payload["ok"] is True
    assert payload["detail"] == "emitted=2"


# ---------------------------------------------------------------------------
# Failure path: ok=False written, result False when GCS itself fails
# ---------------------------------------------------------------------------


def test_heartbeat_ok_false(gcs_store):
    result = write_heartbeat("xsource.sync", ok=False, detail="ConnectionError: timed out")
    assert result is True  # write succeeded; the job failed
    payload = json.loads(gcs_store["heartbeats/xsource.sync/latest.json"])
    assert payload["ok"] is False
    assert "timed out" in payload["detail"]


def test_heartbeat_gcs_failure_returns_false_does_not_raise(monkeypatch):
    """If GCS itself is unreachable, write_heartbeat must return False, not raise."""

    def _bad_client():
        raise OSError("network unreachable")

    monkeypatch.setattr(beat_module, "_storage_client", _bad_client)
    result = write_heartbeat("xsource.watcher", ok=True)
    assert result is False


# ---------------------------------------------------------------------------
# Blob path shape
# ---------------------------------------------------------------------------


def test_blob_path_format(gcs_store):
    write_heartbeat("xsource.watcher", ok=True)
    assert "heartbeats/xsource.watcher/latest.json" in gcs_store


def test_payload_has_ran_at_and_host(gcs_store):
    write_heartbeat("xsource.signals", ok=True)
    payload = json.loads(gcs_store["heartbeats/xsource.signals/latest.json"])
    assert "ran_at" in payload
    assert "host" in payload
