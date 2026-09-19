"""Small SQLite journal; one connection per operation, no shared thread state."""

import json
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, report: dict):
        with self.connect() as db:
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?)",
                (report["id"], report["created_at"], json.dumps(report, allow_nan=False)),
            )

    def list(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM decisions ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
        return [
            {k: d[k] for k in ("id", "created_at", "question", "mode")}
            for (raw,) in rows
            for d in [json.loads(raw)]
        ]

    def get(self, identifier: str):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM decisions WHERE id = ?", (identifier,)).fetchone()
        return json.loads(row[0]) if row else None
