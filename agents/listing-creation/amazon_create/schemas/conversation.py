"""Conversation and human-confirmation state for listing creation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from amazon_create.schemas.workflow import CreationSession


class CandidateStatus(StrEnum):
    """Human confirmation state for one proposed product fact."""

    PENDING = "pending"
    CONFLICT = "conflict"
    CONFIRMED = "confirmed"
    CONFIRMED_MISSING = "confirmed_missing"


class SummaryStatus(StrEnum):
    """Whole-summary confirmation state for v2 conversations."""

    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"


class DialogueIntent(StrEnum):
    """User intent recognized by the conversational orchestrator."""

    PROVIDE_SOURCE = "provide_source"
    CONFIRM = "confirm"
    REVISE = "revise"
    QUESTION = "question"
    CONTINUE = "continue"
    REJECT = "reject"


class DiscussionStatus(StrEnum):
    """Confirmation state of one stage discussion block."""

    PENDING = "pending"
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    STALE = "stale"


class ReActTool(StrEnum):
    """Whitelisted research actions available to the conversational planner."""

    MARKET_RESEARCH = "market_research"
    ASIN_RESEARCH = "asin_research"
    CONTINUE = "continue"


class ReActAction(BaseModel):
    """A validated action chosen for one agent turn; no hidden reasoning is stored."""

    model_config = ConfigDict(frozen=True)

    tool: ReActTool
    label_zh: str


class ReActObservation(BaseModel):
    """Compact, user-visible result of an executed ReAct action."""

    model_config = ConfigDict(frozen=True)

    tool: ReActTool
    status: Literal["complete", "skipped", "degraded", "unavailable"]
    summary_zh: str


class ReActTurn(BaseModel):
    """Auditable plan/action/observation record for a conversational stage turn."""

    model_config = ConfigDict(frozen=True)

    stage: str
    trigger: str
    actions: tuple[ReActAction, ...]
    observations: tuple[ReActObservation, ...]


class DiscussionBlock(BaseModel):
    """One conversational slice of a generated workflow stage."""

    model_config = ConfigDict(frozen=True)

    block_id: str
    stage: str
    title_zh: str
    payload_keys: tuple[str, ...]
    status: DiscussionStatus = DiscussionStatus.PENDING
    revision: int = 1
    confirmed_revision: int = 0


def fact_value_digest(fact_id: str, revision: int, value: str) -> str:
    """Return a stable digest used to reject stale confirmation clicks."""
    raw = f"{fact_id}\0{revision}\0{value.strip()}".encode()
    return hashlib.sha256(raw).hexdigest()


class FactCandidate(BaseModel):
    """One product fact proposed by the user or the reasoning model."""

    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(default_factory=lambda: uuid4().hex)
    key: str
    label_zh: str
    value: str = ""
    group: str = "规格参数"
    required: bool = True
    question_zh: str
    rationale_zh: str = ""
    priority: int = 50
    blocking_stages: tuple[str, ...] = ()
    source_label: str = "user"
    source_quote: str = ""
    conflict_values: tuple[str, ...] = ()
    status: CandidateStatus = CandidateStatus.PENDING
    revision: int = 1
    confirmed_revision: int = 0
    confirmed_digest: str = ""

    @property
    def value_digest(self) -> str:
        return fact_value_digest(self.fact_id, self.revision, self.value)

    @property
    def is_confirmed_current(self) -> bool:
        return (
            self.status in {CandidateStatus.CONFIRMED, CandidateStatus.CONFIRMED_MISSING}
            and self.confirmed_revision == self.revision
            and self.confirmed_digest == self.value_digest
        )


class ConversationMessage(BaseModel):
    """One persisted chat message."""

    model_config = ConfigDict(frozen=True)

    role: Literal["assistant", "user", "system"]
    content: str
    status: Literal["complete", "streaming", "failed"] = "complete"
    stage: str = ""
    block_id: str = ""
    attachments: tuple[dict[str, Any], ...] = ()
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ConversationGraphState(BaseModel):
    """Serializable LangGraph state stored in SQLite checkpoints."""

    model_config = ConfigDict(frozen=False)

    thread_id: str
    schema_version: int = 1
    title: str = "新建 Listing"
    phase: Literal[
        "intake",
        "facts",
        "fact_summary",
        "workflow",
        "completed",
        "legacy_readonly",
    ] = "intake"
    messages: list[ConversationMessage] = Field(default_factory=list)
    candidates: list[FactCandidate] = Field(default_factory=list)
    source_material: str = ""
    current_candidate_id: str = ""
    fact_summary_status: SummaryStatus = SummaryStatus.COLLECTING
    fact_summary_revision: int = 0
    last_intent: DialogueIntent = DialogueIntent.PROVIDE_SOURCE
    discussion_blocks: list[DiscussionBlock] = Field(default_factory=list)
    current_block_id: str = ""
    pending_question_keys: tuple[str, ...] = ()
    rule_hits: list[str] = Field(default_factory=list)
    research_activity: list[str] = Field(default_factory=list)
    react_turns: list[ReActTurn] = Field(default_factory=list)
    facts_revision: int = 0
    generated_fact_revision: int = 0
    category_requirements_signature: str = ""
    asin_research_signature: str = ""
    asin_research_status: str = ""
    downstream_stale: bool = False
    stale_reason_zh: str = ""
    restart_stage: str = ""
    creation_session: CreationSession = Field(default_factory=CreationSession)
    action: dict[str, Any] = Field(default_factory=dict)
    error: str = ""

    @property
    def is_legacy(self) -> bool:
        return self.schema_version < 2

    def current_block(self) -> DiscussionBlock | None:
        return next(
            (item for item in self.discussion_blocks if item.block_id == self.current_block_id),
            None,
        )

    def candidate(self, fact_id: str) -> FactCandidate | None:
        return next((item for item in self.candidates if item.fact_id == fact_id), None)

    def confirmed_candidates(self) -> list[FactCandidate]:
        return [item for item in self.candidates if item.is_confirmed_current]

    def summary_facts(self) -> list[FactCandidate]:
        """Facts with source values included in the one-time summary."""
        return sorted(
            [item for item in self.candidates if item.value.strip()],
            key=lambda item: (item.priority, item.group, item.label_zh),
        )

    def pending_required(self) -> list[FactCandidate]:
        return sorted([
            item
            for item in self.candidates
            if item.required and not item.is_confirmed_current
        ], key=lambda item: (item.priority, item.group, item.label_zh))

    def unresolved_candidates(self) -> list[FactCandidate]:
        """Return every question still visible in the human-review sidebar."""
        return sorted(
            [item for item in self.candidates if not item.is_confirmed_current],
            key=lambda item: (item.priority, item.group, item.label_zh),
        )


class ConversationSnapshot(BaseModel):
    """UI-safe view of one persisted graph thread."""

    model_config = ConfigDict(frozen=True)

    state: ConversationGraphState
    interrupt: dict[str, Any] | None = None


__all__ = [
    "CandidateStatus",
    "ConversationGraphState",
    "ConversationMessage",
    "ConversationSnapshot",
    "DialogueIntent",
    "DiscussionBlock",
    "DiscussionStatus",
    "FactCandidate",
    "ReActAction",
    "ReActObservation",
    "ReActTool",
    "ReActTurn",
    "SummaryStatus",
    "fact_value_digest",
]
