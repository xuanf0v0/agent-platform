"""SQLite-backed service facade for prompt-driven chat."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from amazon_create.config import Settings
from amazon_create.conversation.freeform_graph import (
    build_conversation_graph,
    initial_graph_state,
    stream_reply,
)
from amazon_create.schemas.conversation import ConversationGraphState, ConversationSnapshot


class ConversationStreamEvent:
    """One UI-safe progress or text event emitted during a chat turn."""

    def __init__(self, kind: str, content: str = "") -> None:
        self.kind = kind
        self.content = content


class ConversationService:
    """Manage persistent LangGraph threads without duplicating UI state."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        path = Path(self.settings.checkpoint_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._checkpointer = SqliteSaver(self._connection)
        self._checkpointer.setup()
        self._setup_metadata()
        self._graph = build_conversation_graph(self.settings, self._checkpointer)

    def create_session(self) -> ConversationSnapshot:
        thread_id = uuid4().hex
        state = initial_graph_state(thread_id)
        with self._lock:
            self._graph.invoke(
                {"data": state.model_dump(mode="json"), "action": {"type": "start"}},
                self._config(thread_id),
            )
            self._upsert_metadata(thread_id, state.title)
        return self.snapshot(thread_id)

    def snapshot(self, thread_id: str) -> ConversationSnapshot:
        with self._lock:
            graph_state = self._graph.get_state(self._config(thread_id))
        if not graph_state.values or "data" not in graph_state.values:
            raise KeyError(f"unknown conversation: {thread_id}")
        state = ConversationGraphState.model_validate(graph_state.values["data"])
        interrupt_value = (
            dict(graph_state.interrupts[0].value)
            if graph_state.interrupts
            else None
        )
        return ConversationSnapshot(state=state, interrupt=interrupt_value)

    def send_message(self, thread_id: str, text: str) -> ConversationSnapshot:
        return self._invoke(thread_id, {"type": "message", "text": text})

    def enqueue_message(self, thread_id: str, text: str) -> ConversationSnapshot:
        """Persist a user message immediately, before slow Agent processing."""
        return self._invoke(thread_id, {"type": "enqueue_message", "text": text})

    def stream_pending_turn(
        self,
        thread_id: str,
    ) -> Iterator[ConversationStreamEvent]:
        """Process an already-visible user bubble and stream the assistant reply."""
        before = self.snapshot(thread_id)
        if not before.state.pending_user_message:
            raise ValueError("no pending user message")
        yield ConversationStreamEvent("status", "Agent 正在思考")
        rendered = ""
        for chunk in stream_reply(before.state, self.settings):
            rendered += chunk
            yield ConversationStreamEvent("text", chunk)
        self._invoke(
            thread_id,
            {"type": "complete_streamed_message", "text": rendered},
        )
        yield ConversationStreamEvent("done")

    def rename_session(self, thread_id: str, title: str) -> ConversationSnapshot:
        snapshot = self._invoke(thread_id, {"type": "rename", "title": title})
        with self._lock:
            self._upsert_metadata(thread_id, snapshot.state.title)
        return snapshot

    def delete_session(self, thread_id: str) -> None:
        with self._lock:
            self._checkpointer.delete_thread(thread_id)
            self._connection.execute(
                "DELETE FROM creation_conversations WHERE thread_id = ?",
                (thread_id,),
            )
            self._connection.commit()

    def list_sessions(self) -> list[dict[str, str]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT thread_id, title, created_at, updated_at "
                "FROM creation_conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with suppress(Exception):
            self._connection.close()

    def _invoke(self, thread_id: str, action: dict[str, Any]) -> ConversationSnapshot:
        with self._lock:
            self._graph.invoke({"action": action}, self._config(thread_id))
        return self._after_turn(thread_id)

    def _after_turn(self, thread_id: str) -> ConversationSnapshot:
        snapshot = self.snapshot(thread_id)
        with self._lock:
            self._upsert_metadata(thread_id, snapshot.state.title)
        return snapshot

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    def _setup_metadata(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS creation_conversations (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def _upsert_metadata(self, thread_id: str, title: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO creation_conversations(thread_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at
            """,
            (thread_id, title or "新建 Listing", now, now),
        )
        self._connection.commit()


__all__ = ["ConversationService", "ConversationStreamEvent"]
