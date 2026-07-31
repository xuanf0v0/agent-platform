"""Durable storage for Listing Optimization API runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, cast, final

if TYPE_CHECKING:
    from pydantic import JsonValue


@final
class OptimizationRunStore:
    """Persist the latest public-safe run payload transactionally."""

    def __init__(self, path: str | Path) -> None:
        """Open or create the run database at *path*."""
        self.path: Path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock: RLock = RLock()
        self._connection: sqlite3.Connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            _ = self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_api_runs (
                    run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, run_id: str, payload_json: str, now: str) -> None:
        """Atomically insert or replace one latest run payload."""
        with self._lock, self._connection:
            _ = self._connection.execute(
                """
                INSERT INTO optimization_api_runs(run_id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (run_id, payload_json, now, now),
            )

    def load(self, run_id: str) -> dict[str, JsonValue] | None:
        """Load one run payload, returning ``None`` when absent."""
        with self._lock:
            cursor: sqlite3.Cursor = self._connection.execute(
                "SELECT payload_json FROM optimization_api_runs WHERE run_id = ?",
                (run_id,),
            )
            raw_row = cast("sqlite3.Row | None", cursor.fetchone())
        if raw_row is None:
            return None
        value = cast("JsonValue", json.loads(cast("str", raw_row["payload_json"])))
        if not isinstance(value, dict):
            return None
        return {str(key): item for key, item in value.items()}

    def delete(self, run_id: str) -> bool:
        """Delete one run and report whether it existed."""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM optimization_api_runs WHERE run_id = ?",
                (run_id,),
            )
        return cursor.rowcount > 0

    def close(self) -> None:
        """Close the owned SQLite connection."""
        with self._lock:
            self._connection.close()


__all__ = ["OptimizationRunStore"]
