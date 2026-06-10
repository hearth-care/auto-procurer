from __future__ import annotations

from xsource.watcher.state import ProcessedMessageStore


def test_processed_message_store_is_idempotent(tmp_path):
    path = tmp_path / "watcher.sqlite3"
    state = ProcessedMessageStore(path)

    assert state.seen("msg-1") is False
    state.mark_processed("msg-1", "parsed")
    assert state.seen("msg-1") is True

    reloaded = ProcessedMessageStore(path)
    assert reloaded.seen("msg-1") is True
