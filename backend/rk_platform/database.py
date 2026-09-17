from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def migrate(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, model_id TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'resident', token_count INTEGER NOT NULL DEFAULT 0,
                  reused_tokens INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, request_id TEXT NOT NULL,
                  role TEXT NOT NULL, content TEXT NOT NULL, attachments TEXT NOT NULL DEFAULT '[]',
                  metrics TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                  FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
                  conversation_id TEXT, tool TEXT NOT NULL, arguments TEXT NOT NULL,
                  outcome TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiments (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                  directory TEXT NOT NULL, config TEXT NOT NULL, created_at TEXT NOT NULL,
                  completed_at TEXT
                );
                """
            )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as db:
            db.execute(sql, params)

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def add_message(self, message_id: str, conversation_id: str, request_id: str,
                    role: str, content: str, attachments: list[dict[str, Any]] | None = None,
                    metrics: dict[str, Any] | None = None) -> None:
        self.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, conversation_id, request_id, role, content,
             json.dumps(attachments or [], ensure_ascii=False),
             json.dumps(metrics or {}, ensure_ascii=False), now_iso()),
        )

