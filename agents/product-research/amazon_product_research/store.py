"""Tiny SQLite JSON store for durable research runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import ResearchRun


class RunStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS research_runs (run_id TEXT PRIMARY KEY, title TEXT, status TEXT, updated_at TEXT, payload TEXT NOT NULL)"
            )

    def save(self, run: ResearchRun) -> None:
        run.touch()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO research_runs(run_id,title,status,updated_at,payload) VALUES(?,?,?,?,?)",
                (run.run_id, run.title, run.status.value, run.updated_at, run.model_dump_json()),
            )

    def get(self, run_id: str) -> ResearchRun | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT payload FROM research_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return ResearchRun.model_validate_json(row[0]) if row else None

    def list(self) -> list[dict[str, str]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT run_id,title,status,updated_at FROM research_runs ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {"run_id": row[0], "title": row[1], "status": row[2], "updated_at": row[3]}
            for row in rows
        ]

    def delete(self, run_id: str) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM research_runs WHERE run_id=?", (run_id,))
