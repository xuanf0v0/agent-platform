"""Exhaustive frozen states for the canonical Amazon copy workflow."""

from enum import StrEnum, unique
from typing import Annotated, ClassVar, Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from amazon_copy.schemas.canonical_deliverables import (
    AuditDeliverable,
    CanonicalDeliverable,
    DeliverableKind,
)
from amazon_copy.schemas.canonical_models import NonBlankText


class FrozenWorkflowModel(BaseModel):
    """Immutable strict base for serialized workflow values."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


@unique
class WorkflowStatus(StrEnum):
    """Closed state set for staged copy optimization."""

    AUDIT_READY = "audit_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_FACTS = "awaiting_facts"
    CONTINUATION_AUTHORIZED = "continuation_authorized"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@unique
class AuthorizationScope(StrEnum):
    """Seller approval scope carried into generation."""

    SINGLE = "single"
    BATCH = "batch"


@unique
class FailureCode(StrEnum):
    """Safe terminal reasons that never imply deliverable success."""

    CANCELLED = "cancelled"
    VALIDATION_FAILED = "validation_failed"
    GENERATION_FAILED = "generation_failed"
    POSTFLIGHT_BLOCKED = "postflight_blocked"


class WorkflowQuestion(FrozenWorkflowModel):
    """One targeted fact question required before continuation."""

    code: NonBlankText
    field: NonBlankText
    prompt: NonBlankText
    evidence_ids: tuple[NonBlankText, ...] = ()


class ContinuationAuthorization(FrozenWorkflowModel):
    """Revision-bound seller authorization for one continuation token."""

    continuation_id: NonBlankText
    expected_revision: int = Field(ge=0)
    scope: AuthorizationScope
    authorized_at: AwareDatetime


class AuditReady(FrozenWorkflowModel):
    """Stage 1 audit is complete and ready to present."""

    state: Literal[WorkflowStatus.AUDIT_READY] = WorkflowStatus.AUDIT_READY
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    audit: AuditDeliverable


class AwaitingApproval(FrozenWorkflowModel):
    """Audit is visible and generation awaits seller authorization."""

    state: Literal[WorkflowStatus.AWAITING_APPROVAL] = WorkflowStatus.AWAITING_APPROVAL
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    audit: AuditDeliverable
    target: DeliverableKind
    continuation_id: NonBlankText


class AwaitingFacts(FrozenWorkflowModel):
    """Workflow is paused on one or more targeted fact questions."""

    state: Literal[WorkflowStatus.AWAITING_FACTS] = WorkflowStatus.AWAITING_FACTS
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    audit: AuditDeliverable
    target: DeliverableKind
    continuation_id: NonBlankText
    questions: tuple[WorkflowQuestion, ...] = Field(min_length=1)


class ContinuationAuthorized(FrozenWorkflowModel):
    """Approval or answered facts authorize the requested output."""

    state: Literal[WorkflowStatus.CONTINUATION_AUTHORIZED] = WorkflowStatus.CONTINUATION_AUTHORIZED
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    audit: AuditDeliverable
    target: DeliverableKind
    authorization: ContinuationAuthorization


class Generating(FrozenWorkflowModel):
    """Authorized deliverable generation is in progress."""

    state: Literal[WorkflowStatus.GENERATING] = WorkflowStatus.GENERATING
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    audit: AuditDeliverable
    target: DeliverableKind
    authorization: ContinuationAuthorization


class Completed(FrozenWorkflowModel):
    """Requested deliverable completed and passed its workflow boundary."""

    state: Literal[WorkflowStatus.COMPLETED] = WorkflowStatus.COMPLETED
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    deliverable: CanonicalDeliverable


class Failed(FrozenWorkflowModel):
    """Terminal state with no implied publishable output."""

    state: Literal[WorkflowStatus.FAILED] = WorkflowStatus.FAILED
    workflow_id: NonBlankText
    revision: int = Field(ge=0)
    code: FailureCode
    message: NonBlankText
    recoverable: bool


WorkflowState: TypeAlias = Annotated[
    AuditReady
    | AwaitingApproval
    | AwaitingFacts
    | ContinuationAuthorized
    | Generating
    | Completed
    | Failed,
    Field(discriminator="state"),
]


def workflow_status(state: WorkflowState) -> WorkflowStatus:
    """Return the validated state discriminator."""
    return state.state


__all__ = [
    "AuditReady",
    "AuthorizationScope",
    "AwaitingApproval",
    "AwaitingFacts",
    "Completed",
    "ContinuationAuthorization",
    "ContinuationAuthorized",
    "Failed",
    "FailureCode",
    "FrozenWorkflowModel",
    "Generating",
    "WorkflowQuestion",
    "WorkflowState",
    "WorkflowStatus",
    "workflow_status",
]
