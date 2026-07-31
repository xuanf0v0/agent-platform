"""Durable storage for Listing Optimization API runs."""

from __future__ import annotations

import json
import re
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
                    title TEXT NOT NULL DEFAULT '新建优化',
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_index_columns()
            self._backfill_index_columns()

    def save(
        self,
        run_id: str,
        payload_json: str,
        now: str,
        *,
        title: str,
        status: str,
    ) -> None:
        """Atomically insert or replace one latest run payload."""
        with self._lock, self._connection:
            _ = self._connection.execute(
                """
                INSERT INTO optimization_api_runs(
                    run_id, payload_json, title, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    title=excluded.title,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (run_id, payload_json, title, status, now, now),
            )

    def rename(self, run_id: str, title: str, now: str) -> bool:
        """Rename one indexed run without loading its full payload."""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE optimization_api_runs SET title = ?, updated_at = ? WHERE run_id = ?",
                (title, now, run_id),
            )
        return cursor.rowcount > 0

    def list_summaries(self) -> list[dict[str, str]]:
        """Return lightweight history rows ordered by latest activity."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT run_id, title, status, created_at, updated_at "
                "FROM optimization_api_runs ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {
                "run_id": str(row["run_id"]),
                "title": str(row["title"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        ]

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

    def _migrate_index_columns(self) -> None:
        columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(optimization_api_runs)"
            ).fetchall()
        }
        if "title" not in columns:
            _ = self._connection.execute(
                "ALTER TABLE optimization_api_runs "
                "ADD COLUMN title TEXT NOT NULL DEFAULT '新建优化'"
            )
        if "status" not in columns:
            _ = self._connection.execute(
                "ALTER TABLE optimization_api_runs "
                "ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"
            )

    def _backfill_index_columns(self) -> None:
        rows = self._connection.execute(
            "SELECT run_id, payload_json, title, status FROM optimization_api_runs"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            title = str(row["title"] or "").strip()
            status = str(row["status"] or "").strip()
            source_text = str(payload.get("source_text") or "")
            stored_title = str(payload.get("title") or "").strip()
            resolved_title = (
                stored_title
                or (default_run_title(source_text) if title == "新建优化" else title)
            )
            resolved_status = str(payload.get("status") or status or "queued")
            _ = self._connection.execute(
                "UPDATE optimization_api_runs SET title = ?, status = ? WHERE run_id = ?",
                (resolved_title, resolved_status, str(row["run_id"])),
            )


_TITLE_LABEL = re.compile(r"^\s*(?:标题|title)\s*[:\uFF1A]\s*", re.IGNORECASE)


def default_run_title(source_text: str) -> str:
    """Build one stable compact history title from the submitted Listing."""
    first_line = next((line.strip() for line in source_text.splitlines() if line.strip()), "")
    cleaned = _TITLE_LABEL.sub("", first_line).strip()
    return (cleaned or "新建优化")[:80]


__all__ = ["OptimizationRunStore", "default_run_title"]
