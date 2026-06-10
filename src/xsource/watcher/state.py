"""SQLite idempotency store for the xsource reply watcher."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class ProcessedMessageStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def seen(self, message_id: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return row is not None

    def mark_processed(self, message_id: str, action: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO processed_messages (message_id, action)
                VALUES (?, ?)
                """,
                (message_id, action),
            )

