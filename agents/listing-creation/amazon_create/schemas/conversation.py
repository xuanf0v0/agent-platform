"""Minimal persisted state for prompt-driven Listing creation chat."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessage(BaseModel):
    """One persisted chat message."""

    model_config = ConfigDict(frozen=True)

    role: Literal["assistant", "user", "system"]
    content: str
    status: Literal["complete", "streaming", "failed"] = "complete"
    attachments: tuple[dict[str, Any], ...] = ()
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ConfirmedFact(BaseModel):
    """One product fact explicitly supplied or approved by the user."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    value: str
    group: str = "产品信息"
    source_quote: str = ""


class ConversationGraphState(BaseModel):
    """Serializable message state stored by the LangGraph checkpointer."""

    model_config = ConfigDict(frozen=False, extra="ignore")

    thread_id: str
    schema_version: int = 3
    title: str = "新建 Listing"
    asin: str = ""
    messages: list[ConversationMessage] = Field(default_factory=list)
    confirmed_facts: list[ConfirmedFact] = Field(default_factory=list)
    pending_user_message: str = ""
    error: str = ""


class ConversationSnapshot(BaseModel):
    """UI-safe view of one persisted graph thread."""

    model_config = ConfigDict(frozen=True)

    state: ConversationGraphState
    interrupt: dict[str, Any] | None = None


__all__ = [
    "ConfirmedFact",
    "ConversationGraphState",
    "ConversationMessage",
    "ConversationSnapshot",
]
