"""SQLite-backed service facade for the conversational Streamlit UI."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from threading import RLock, Thread
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from amazon_create.config import Settings
from amazon_create.conversation.graph import build_conversation_graph, initial_graph_state
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
        snapshot = self.snapshot(thread_id)
        if snapshot.state.is_legacy:
            return snapshot
        return self._invoke(thread_id, {"type": "message", "text": text})

    def stream_message(
        self,
        thread_id: str,
        text: str,
        *,
        chunk_chars: int = 48,
    ) -> tuple[ConversationSnapshot, Iterator[str]]:
        """Process atomically, then stream only the newly persisted assistant reply."""
        before = self.snapshot(thread_id)
        snapshot = self.send_message(thread_id, text)
        new_messages = snapshot.state.messages[len(before.state.messages) :]
        reply = "\n\n".join(
            message.content for message in new_messages if message.role == "assistant"
        )

        def chunks() -> Iterator[str]:
            size = max(1, chunk_chars)
            for index in range(0, len(reply), size):
                yield reply[index : index + size]

        return snapshot, chunks()

    def stream_turn(
        self,
        thread_id: str,
        text: str,
        *,
        chunk_chars: int = 48,
        status_interval_seconds: float = 0.35,
    ) -> Iterator[ConversationStreamEvent]:
        """Execute a turn in the background while yielding visible UI progress.

        Conversation state is persisted only after the graph finishes. The stream
        therefore never leaves partial assistant messages in SQLite, while the UI
        receives progress immediately instead of waiting on a blocking graph call.
        """
        before = self.snapshot(thread_id)
        events: Queue[tuple[str, Any]] = Queue()

        def run() -> None:
            try:
                snapshot = self.send_message(thread_id, text)
            except Exception as exc:  # noqa: BLE001
                events.put(("error", exc))
            else:
                events.put(("complete", snapshot))

        worker = Thread(target=run, name=f"creation-turn-{thread_id[:8]}", daemon=True)
        yield ConversationStreamEvent("status", "已收到消息，正在读取并核对已确认事实")
        worker.start()
        status_index = 0
        running_statuses = (
            "正在提取产品事实与识别待确认信息",
            "正在按规则执行当前工作流阶段",
            "正在进行受控研究与生成可验证结论",
            "正在整理本轮回复，请稍候",
        )

        while worker.is_alive() or not events.empty():
            try:
                kind, payload = events.get(timeout=status_interval_seconds)
            except Empty:
                yield ConversationStreamEvent("status", running_statuses[status_index])
                status_index = (status_index + 1) % len(running_statuses)
                continue
            if kind == "status":
                yield ConversationStreamEvent("status", str(payload))
                continue
            if kind == "error":
                raise payload

            snapshot = payload
            new_messages = snapshot.state.messages[len(before.state.messages) :]
            reply = "\n\n".join(
                message.content for message in new_messages if message.role == "assistant"
            )
            size = max(1, chunk_chars)
            for index in range(0, len(reply), size):
                yield ConversationStreamEvent("text", reply[index : index + size])
            yield ConversationStreamEvent("done")
            return

    def confirm_current(self, thread_id: str) -> ConversationSnapshot:
        """Compatibility helper; v2 uses a normal chat confirmation."""
        return self.send_message(thread_id, "确认")

    def confirm_fact(
        self,
        thread_id: str,
        *,
        fact_id: str,
        revision: int,
        value_digest: str,
    ) -> ConversationSnapshot:
        """Retain the legacy signature while using summary-level confirmation."""
        _ = (fact_id, revision, value_digest)
        return self.send_message(thread_id, "确认")

    def confirm_unavailable(self, thread_id: str) -> ConversationSnapshot:
        return self.send_message(thread_id, "当前无法提供，请标记为待确认")

    def revise_fact(self, thread_id: str, fact_id: str, value: str) -> ConversationSnapshot:
        return self._invoke(
            thread_id,
            {"type": "revise_fact", "fact_id": fact_id, "value": value},
        )

    def regenerate(self, thread_id: str) -> ConversationSnapshot:
        return self._invoke(thread_id, {"type": "regenerate"})

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
